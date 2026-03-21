from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

from loguru import logger

DEFAULT_LOGURU_SINK_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS Z}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
)

# Subprocess output (e.g. podman build lines) — grey in console, plain in file
SUBPROCESS_FMT = "<light-black>{message}</light-black>"

# Maximum number of timestamped log files to retain
LOG_RETENTION_COUNT = 10


def _prune_old_logs(log_dir: Path, keep: int = LOG_RETENTION_COUNT) -> None:
    """Delete oldest cutip-*.log files, keeping the most recent *keep*."""
    logs = sorted(log_dir.glob("cutip-*.log"), key=lambda p: p.name)
    for old in logs[:-keep]:
        old.unlink(missing_ok=True)


def setup_logging(log_dir: Path | None = None, level: str = "INFO") -> str | None:
    """Configure loguru sinks for CUTIP.

    Four sinks are registered:

    1. Console — subprocess lines in grey  (``logger.bind(subprocess=True)``)
    2. File    — subprocess lines as plain ``{message}`` (no timestamps)
    3. Console — standard CUTIP lines with full DEFAULT_LOGURU_SINK_FORMAT
    4. File    — standard CUTIP lines with full DEFAULT_LOGURU_SINK_FORMAT

    Sinks 2 and 4 are only added when *log_dir* is provided.
    Each run creates a new timestamped log file (e.g. ``cutip-20260319T143052.log``).
    Old log files beyond :data:`LOG_RETENTION_COUNT` are pruned automatically.

    Returns the log file path if file logging was set up, else None.
    """
    logger.remove()

    is_subprocess = lambda rec: rec["extra"].get("subprocess") is True  # noqa: E731
    is_standard = lambda rec: not rec["extra"].get("subprocess")  # noqa: E731

    # 1) Console: subprocess lines in grey
    logger.add(
        sys.stdout,
        colorize=True,
        format=SUBPROCESS_FMT,
        level="DEBUG",
        filter=is_subprocess,
    )

    # 3) Console: standard lines with full format
    logger.add(
        sys.stdout,
        colorize=True,
        format=DEFAULT_LOGURU_SINK_FORMAT,
        level=level,
        filter=is_standard,
    )

    if log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)

        # Timestamped log file per run
        ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
        log_file = log_dir / f"cutip-{ts}.log"

        # 2) File: subprocess lines as plain text (no decoration)
        logger.add(
            str(log_file),
            colorize=False,
            format="{message}",
            level="DEBUG",
            filter=is_subprocess,
        )

        # 4) File: standard lines with full format
        logger.add(
            str(log_file),
            colorize=False,
            format=DEFAULT_LOGURU_SINK_FORMAT,
            level="DEBUG",
            encoding="utf-8",
            filter=is_standard,
        )

        # Prune old log files
        _prune_old_logs(log_dir)

        return str(log_file)

    return None
