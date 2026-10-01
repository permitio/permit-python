from loguru import logger

from permit.config import PermitConfig
from permit.utils.sdk_logger import sdk_logger

PERMIT_MODULE = "permit"


def configure_logger(config: PermitConfig) -> None:
    """Silence the SDK's loguru output unless the config enables logging.

    Whatever the settings, the API key in `config.token` is replaced with `[REDACTED]` in
    every record the SDK logs from now on, the records of other clients included.

    Args:
        config: The SDK configuration; `config.log.enable` and `config.token` are read.
    """
    sdk_logger.redact(config.token)
    if not config.log.enable:
        logger.disable(PERMIT_MODULE)
