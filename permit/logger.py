import sys

from loguru import logger

from .config import PermitConfig

PERMIT_MODULE = "permit"


def configure_logger(config: PermitConfig):
    if config.log.enable:
        logger.add(
            sys.stderr,
            format="{time} {level} {message}",
            filter=PERMIT_MODULE,
            level=config.log.level.upper(),
            serialize=config.log.log_as_json,
        )
    else:
        logger.disable(PERMIT_MODULE)
