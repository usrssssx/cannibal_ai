from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger

from .config import Settings


def configure_logging(settings: Settings) -> None:
    logger.remove()
    logger.add(sys.stderr, level=settings.log_level)
    if settings.log_file:
        log_path = Path(settings.log_file)
        if log_path.parent:
            log_path.parent.mkdir(parents=True, exist_ok=True)
        logger.add(
            str(log_path),
            level=settings.log_level,
            rotation=settings.log_rotation,
            retention=settings.log_retention,
            encoding="utf-8",
        )
