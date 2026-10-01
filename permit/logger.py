import contextlib

from loguru import logger

from permit.config import PermitConfig
from permit.utils.sdk_logger import sdk_logger

PERMIT_MODULE = "permit"

# The names Python's logging module also accepts, and the ones the Node SDK's logger uses.
_LEVEL_ALIASES = {"WARN": "WARNING", "FATAL": "CRITICAL"}


def configure_logger(config: PermitConfig) -> None:
    """Apply the `log` settings of `config` to the SDK's log records.

    The settings are process-wide, as loguru's logger is: the client created last decides
    whether the SDK logs, and the last one created with `log.enable` True decides the level
    and the label, for every client. The SDK adds no sink and leaves the application's sinks
    and levels alone, so its records are written wherever loguru writes the application's,
    in the format of those sinks.

    - `log.enable` False calls `logger.disable("permit")`, so nothing is logged; True calls
      `logger.enable("permit")`.
    - `log.level` drops the SDK's records below that severity before they reach any sink.
    - `log.label` is put in brackets before each message.
    - `log.log_as_json` is not applied: loguru serializes per sink, with
      `logger.add(..., serialize=True)`.

    Whatever the settings, the API key in `config.token` is replaced with `[REDACTED]` in
    every message the SDK logs and in the PDP error bodies it puts in a
    `PermitConnectionError`.

    Args:
        config: The SDK configuration.

    Raises:
        ValueError: If `log.enable` is True and `log.level` is not the name of a loguru level.
    """
    sdk_logger.redact(config.token)
    if not config.log.enable:
        logger.disable(PERMIT_MODULE)
        return
    sdk_logger.configure(min_level_no=_level_no(config.log.level), label=config.log.label)
    logger.enable(PERMIT_MODULE)


def _level_no(level: str) -> int:
    upper = level.upper()
    # loguru's level names are case-sensitive: try the name as given first, so a level the
    # application added in lower case is found, then the upper-case name of a built-in one.
    for name in (level, _LEVEL_ALIASES.get(upper, upper)):
        with contextlib.suppress(ValueError):
            return logger.level(name).no
    msg = (
        f"Invalid log level {level!r} in the Permit SDK config (log.level): use trace, "
        "debug, info, success, warning, error or critical, or a level added with "
        "loguru's logger.level()."
    )
    raise ValueError(msg)
