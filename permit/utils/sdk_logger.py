import threading

from loguru import logger

REDACTED = "[REDACTED]"


class SdkLogger:
    """Logs the SDK's own records to loguru's logger, without the API keys in them.

    Each record reaches loguru from the SDK module that logged it, so
    `logger.disable("permit")`, `logger.enable("permit")` and the application's sinks treat
    it as a record of that module. On the way, this replaces every registered API key with
    `[REDACTED]`.

    The registered keys are process-wide, like loguru's logger.
    """

    def __init__(self) -> None:
        self._secrets_lock = threading.Lock()
        # Replaced, never mutated, so a thread that logs while another registers a secret
        # reads either the old set or the new one.
        self._secrets: frozenset[str] = frozenset()

    def redact(self, secret: str) -> None:
        """Replace `secret` with `[REDACTED]` in every record logged from now on.

        Args:
            secret: A credential, such as an API key. An empty string is ignored.
        """
        if not secret:
            return
        with self._secrets_lock:
            self._secrets |= {secret}

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
        for secret in self._secrets:
            message = message.replace(secret, REDACTED)
        # depth=2 skips this method and the one that called it, so loguru attributes the
        # record to the SDK module that logged it. The message goes without arguments, so
        # loguru does not call str.format on it and braces in it are kept as they are.
        logger.opt(depth=2).log(level, message)


sdk_logger = SdkLogger()
