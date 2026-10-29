import threading
from collections.abc import Callable
from typing import TypeAlias
from urllib.parse import urlsplit, urlunsplit

from loguru import logger

REDACTED = "[REDACTED]"
# A secret shorter than this is not redacted: replacing a short value such as "token" in
# every message would mangle the SDK's own text. Permit API keys are far longer.
MIN_SECRET_LENGTH = 12
# The package whose records loguru's logger.enable() and logger.disable() switch on and off.
PACKAGE = "permit"

# A message, or a function that builds it, for a message costly to build: it is called
# only for a record that some sink will receive.
Message: TypeAlias = str | Callable[[], str]


class SdkLogger:
    """Logs the SDK's own records to loguru's logger, applying the SDK's `log` settings.

    Each record reaches loguru from the SDK module that logged it, so
    `logger.disable("permit")`, `logger.enable("permit")` and the application's sinks treat
    it as a record of that module. On the way, this drops records below the minimum
    severity. For a record loguru passes on, the message is then built, prefixed with the
    label and has every registered API key replaced with `[REDACTED]`; for one it drops,
    while the package is disabled or below every sink's level, none of that is done.

    Its settings are process-wide, like loguru's logger. Until `enable` is called, it
    keeps every record and adds no label.
    """

    def __init__(self) -> None:
        self._min_level_no = 0
        self._label = ""
        # Whether `disable` called logger.disable("permit") after the last `enable`.
        self._disabled_package = False
        # Held while the loguru switch and `_disabled_package` change together, so two
        # clients created at once in different threads leave them consistent.
        self._switch_lock = threading.Lock()
        self._secrets_lock = threading.Lock()
        # Longest first: where one secret contains another, such as a key and a prefix of
        # it, the whole of the longer one is replaced, not just the shorter part. Replaced,
        # never mutated, so a thread that logs while another registers a secret reads
        # either the old tuple or the new one.
        self._secrets: tuple[str, ...] = ()

    def disable(self) -> None:
        """Stop loguru from passing on any record of the package: `logger.disable("permit")`."""
        with self._switch_lock:
            logger.disable(PACKAGE)
            self._disabled_package = True

    def enable(self, *, min_level_no: int, label: str) -> None:
        """Keep the records from `min_level_no` up, with `label` before each message.

        If `disable` was called since the last `enable`, this undoes it with
        `logger.enable("permit")`, which also drops every `logger.disable` set for a module
        of the package and overrides an application-wide `logger.disable("")` for its
        records. Otherwise it leaves loguru's switches alone, so those still apply.

        Args:
            min_level_no: The loguru severity number below which records are dropped.
            label: The text put in brackets before each message; an empty string adds none.
        """
        with self._switch_lock:
            self._min_level_no = min_level_no
            self._label = label
            if self._disabled_package:
                logger.enable(PACKAGE)
                self._disabled_package = False

    def redact(self, secret: str) -> None:
        """Replace `secret` with `[REDACTED]` in every record logged from now on.

        The secret without its leading and trailing whitespace is replaced too: a key read
        from a file or an environment variable may end with a space, which an HTTP server
        that echoes the key back has stripped. So is each in lower case: aiohttp lower-cases
        some of the server text it puts in its error messages, such as a Content-Type.

        Args:
            secret: A credential, such as an API key. A secret shorter than
                `MIN_SECRET_LENGTH` without its surrounding whitespace is ignored.
        """
        trimmed = secret.strip()
        if len(trimmed) < MIN_SECRET_LENGTH:
            return
        with self._secrets_lock:
            new = {secret, trimmed, secret.lower(), trimmed.lower()}.difference(self._secrets)
            if new:
                self._secrets = tuple(sorted((*self._secrets, *new), key=len, reverse=True))

    def scrub(self, text: str) -> str:
        """Return `text` with every registered secret replaced with `[REDACTED]`.

        Args:
            text: Any text the SDK logs or puts in an exception.

        Returns:
            The text without any registered secret.
        """
        for secret in self._secrets:
            text = text.replace(secret, REDACTED)
        return text

    def scrub_bytes(self, data: bytes) -> bytes:
        """Return `data` with every registered secret, UTF-8 encoded, replaced.

        Args:
            data: Bytes a server sent, such as an HTTP line an aiohttp error keeps.

        Returns:
            The bytes without any registered secret.
        """
        for secret in self._secrets:
            data = data.replace(secret.encode(), REDACTED.encode())
        return data

    def debug(self, message: Message) -> None:
        """Log `message` with severity DEBUG."""
        self._log("DEBUG", message)

    def warning(self, message: Message) -> None:
        """Log `message` with severity WARNING."""
        self._log("WARNING", message)

    def error(self, message: Message) -> None:
        """Log `message` with severity ERROR."""
        self._log("ERROR", message)

    def _log(self, level: str, message: Message) -> None:
        if logger.level(level).no < self._min_level_no:
            return
        label = self._label
        # depth=2 skips this method and the one that called it, so loguru attributes the
        # record to the SDK module that logged it. lazy=True: loguru calls the function
        # only once its enabled and level checks pass, so a record it drops is never built
        # or scrubbed. The message is the argument of "{}", so braces in it are kept.
        logger.opt(depth=2, lazy=True).log(level, "{}", lambda: self._render(message, label))

    def _render(self, message: Message, label: str) -> str:
        text = message() if callable(message) else message
        if label:
            text = f"[{label}] {text}"
        # After the label goes on, so a key in the label is replaced too.
        return self.scrub(text)


def without_userinfo(url: str) -> str:
    """`url` without a user name or password, which a proxy URL may carry.

    For a log line or an exception message: it never raises, and a URL it can't parse
    comes back as `<invalid URL>`.
    """
    try:
        parts = urlsplit(url)
    except ValueError:
        return "<invalid URL>"
    if "@" not in parts.netloc:
        return url
    return urlunsplit(parts._replace(netloc=parts.netloc.rpartition("@")[2]))


sdk_logger = SdkLogger()
