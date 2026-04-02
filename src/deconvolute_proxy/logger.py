import logging
import sys


def get_logger(name: str | None = None) -> logging.Logger:
    logger = logging.getLogger(
        "deconvolute_proxy" if not name else f"deconvolute_proxy.{name}"
    )
    return logger


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)s  %(name)s  %(message)s",
        stream=sys.stdout,
    )
