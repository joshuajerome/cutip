from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger


DEFAULT_LOGURU_SINK_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS Z}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
)


def setup_logging(log_dir: Path | None = None, level: str = "INFO") -> None:
    """Configure loguru sinks for CUTIP.

    Console sink at INFO (or overridden level).
    File sink at DEBUG when log_dir is provided (written to log_dir/cutip.log).
    """
    logger.remove()

    logger.add(
        sys.stdout,
        level=level,
        format=DEFAULT_LOGURU_SINK_FORMAT,
        colorize=True,
    )

    if log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)
        logger.add(
            log_dir / "cutip.log",
            level="DEBUG",
            format=DEFAULT_LOGURU_SINK_FORMAT,
            colorize=False,
            rotation="10 MB",
            retention=5,
            encoding="utf-8",
        )
