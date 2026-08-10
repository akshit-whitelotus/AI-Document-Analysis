import logging

import structlog

logging.basicConfig(level=logging.INFO)


def get_logger(name: str):
    return structlog.get_logger(name)