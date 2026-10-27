import contextlib
import contextvars
import threading

from loguru import logger

from permit.config import PermitConfig
from permit.utils.sdk_logger import PACKAGE, sdk_logger

PERMIT_MODULE = PACKAGE

# The names Python's logging module also accepts, and the ones the Node SDK's logger uses.
_LEVEL_ALIASES = {"WARN": "WARNING", "FATAL": "CRITICAL"}

# Set while a client derives another from itself (`Permit.wait_for_sync`): the derived
# client keeps the process's log settings instead of applying its own again.
keep_log_settings: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "permit_keep_log_settings", default=False
)

# The unknown level names already warned about, so a process that creates a client per
# request warns once per name.
_warned_levels: set[str] = set()
_warned_levels_lock = threading.Lock()


def configure_logger(config: PermitConfig) -> None:
    """Apply the `log` settings of `config` to the SDK's log records.

    The settings are process-wide, as loguru's logger is: the client created last decides
    whether the SDK logs, and the last one created with `log.enable` True decides the level
    and the label, for every client. The SDK adds no sink and leaves the application's sinks
    and levels alone, so its records are written wherever loguru writes the application's,
    in the format of those sinks.

    - `log.enable` False calls `logger.disable("permit")`, so nothing is logged. True
      undoes that call with `logger.enable("permit")` if an earlier client made it, and
      otherwise leaves loguru's switches alone, so a `logger.disable` the application made
      for the package or one of its modules still applies.
    - `log.level` drops the SDK's records below that severity before they reach any sink.
    - `log.label` is put in brackets before each message.
    - `log.log_as_json` is not applied: loguru serializes per sink. For JSON output, the
      application replaces loguru's default sink with a serialized one: `logger.remove()`,
      then `logger.add(sys.stderr, serialize=True)`.

    Whatever the settings, the API key in `config.token` is replaced with `[REDACTED]` in
    every message the SDK logs and in the error bodies it puts in the exceptions it raises.

    `log.level` is a level name, in any case, or a loguru severity number. An unknown one
    does not fail client creation: the SDK logs a warning that names the value, once per
    process, and uses INFO.

    While `keep_log_settings` is set (`Permit.wait_for_sync` deriving a client), only the
    key is registered for redaction: the process's log settings stay as they are.

    Args:
        config: The SDK configuration.
    """
    sdk_logger.redact(config.token)
    if keep_log_settings.get():
        return
    if not config.log.enable:
        sdk_logger.disable()
        return
    level_no = _level_no(config.log.level)
    if level_no is None:
        sdk_logger.enable(min_level_no=logger.level("INFO").no, label=config.log.label)
        with _warned_levels_lock:
            if config.log.level in _warned_levels:
                return
            _warned_levels.add(config.log.level)
        sdk_logger.warning(
            f"Unknown log level {config.log.level!r} in the Permit SDK config (log.level), "
            "so the SDK logs at INFO. Use trace, debug, info, success, warning, error or "
            "critical, or a level added with loguru's logger.level()."
        )
        return
    sdk_logger.enable(min_level_no=level_no, label=config.log.label)


def _level_no(level: str) -> int | None:
    level = level.strip()
    # A severity number, as loguru accepts it (pydantic turns `10` into "10").
    if level.isdigit():
        return int(level)
    upper = level.upper()
    # loguru's level names are case-sensitive: try the name as given first, so a level the
    # application added in lower case is found, then the upper-case name of a built-in one.
    for name in (level, _LEVEL_ALIASES.get(upper, upper)):
        with contextlib.suppress(ValueError):
            return logger.level(name).no
    return None
