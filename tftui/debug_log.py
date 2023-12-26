import logging


def setup_logging(log_level=None):
    logger = logging.getLogger(__name__)
    if log_level is not None:
        numeric_level = getattr(logging, log_level.upper(), None)
        logger.setLevel(numeric_level)
        if not logger.handlers:
            formatter = logging.Formatter(
                "%(asctime)s [%(module)s:%(funcName)s] %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
            file_handler = logging.FileHandler("tftui.log")
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)

    return logger
