import threading

from loguru import logger

REDACTED = "[REDACTED]"
# The package whose records loguru's logger.enable() and logger.disable() switch on and off.
PACKAGE = "permit"


class SdkLogger:
    """Logs the SDK's own records to loguru's logger, applying the SDK's `log` settings.

    Each record reaches loguru from the SDK module that logged it, so
    `logger.disable("permit")`, `logger.enable("permit")` and the application's sinks treat
    it as a record of that module. On the way, this drops records below the minimum
    severity, replaces every registered API key with `[REDACTED]` and prefixes the message
    with the label.

    Its settings are process-wide, like loguru's logger. Until `enable` is called, it
    keeps every record and adds no label.
    """

    def __init__(self) -> None:
        self._min_level_no = 0
        self._label = ""
        # Whether `disable` called logger.disable("permit") after the last `enable`.
        self._disabled_package = False
        self._secrets_lock = threading.Lock()
        # Longest first: where one secret contains another, such as a key and a prefix of
        # it, the whole of the longer one is replaced, not just the shorter part. Replaced,
        # never mutated, so a thread that logs while another registers a secret reads
        # either the old tuple or the new one.
        self._secrets: tuple[str, ...] = ()

    def disable(self) -> None:
        """Stop loguru from passing on any record of the package: `logger.disable("permit")`."""
        logger.disable(PACKAGE)
        self._disabled_package = True

    def enable(self, *, min_level_no: int, label: str) -> None:
        """Keep the records from `min_level_no` up, with `label` before each message.

        If `disable` was called since the last `enable`, this undoes it with
        `logger.enable("permit")`. Otherwise it leaves loguru's switches alone: loguru's
        enable would also drop every `logger.disable` the application set for a module of
        the package, and override an application-wide `logger.disable("")`.

        Args:
            min_level_no: The loguru severity number below which records are dropped.
            label: The text put in brackets before each message; an empty string adds none.
        """
        self._min_level_no = min_level_no
        self._label = label
        if self._disabled_package:
            logger.enable(PACKAGE)
            self._disabled_package = False

    def redact(self, secret: str) -> None:
        """Replace `secret` with `[REDACTED]` in every record logged from now on.

        The secret without its leading and trailing whitespace is replaced too: a key read
        from a file or an environment variable may end with a space, which an HTTP server
        that echoes the key back has stripped.

        Args:
            secret: A credential, such as an API key. A secret that is empty or only
                whitespace is ignored.
        """
        trimmed = secret.strip()
        if not trimmed:
            return
        with self._secrets_lock:
            new = {secret, trimmed}.difference(self._secrets)
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

    def debug(self, message: str) -> None:
        """Log `message` with severity DEBUG."""
        self._log("DEBUG", message)

    def warning(self, message: str) -> None:
        """Log `message` with severity WARNING."""
        self._log("WARNING", message)

    def error(self, message: str) -> None:
        """Log `message` with severity ERROR."""
        self._log("ERROR", message)

    def _log(self, level: str, message: str) -> None:
        if logger.level(level).no < self._min_level_no:
            return
        message = self.scrub(message)
        if self._label:
            message = f"[{self._label}] {message}"
        # depth=2 skips this method and the one that called it, so loguru attributes the
        # record to the SDK module that logged it. The message goes without arguments, so
        # loguru does not call str.format on it and braces in it are kept as they are.
        logger.opt(depth=2).log(level, message)


sdk_logger = SdkLogger()
