import sys

from loguru import logger

from .config import PermitConfig

PERMIT_MODULE = "permit"


def configure_logger(config: PermitConfig):
    if not config.log.enable:
        logger.disable(PERMIT_MODULE)
