from __future__ import annotations

from loguru import logger


def configure_logging(level: str = "INFO") -> None:
    logger.remove()
    logger.add(
        sink=lambda msg: print(msg, end=""),
        level=level,
        serialize=True,
    )
