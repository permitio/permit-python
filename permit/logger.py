from loguru import logger

from permit.config import PermitConfig

PERMIT_MODULE = "permit"


def configure_logger(config: PermitConfig) -> None:
    """Silence the SDK's loguru output unless the config enables logging.

    Args:
        config: The SDK configuration; only `config.log.enable` is read.
    """
    if not config.log.enable:
        logger.disable(PERMIT_MODULE)
