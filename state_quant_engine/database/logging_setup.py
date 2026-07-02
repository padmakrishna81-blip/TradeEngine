"""Application logging setup with loguru."""
from __future__ import annotations
import os
import sys
from loguru import logger


def setup_logging(log_path: str = "logs/sqe.log", level: str = "INFO",
                   rotation: str = "1 day", retention: str = "30 days") -> None:
    """Configure loguru with file and console sinks."""
    os.makedirs(os.path.dirname(log_path) if os.path.dirname(log_path) else ".", exist_ok=True)
    logger.remove()
    logger.add(sys.stderr, level=level, format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>")
    logger.add(log_path, level=level, rotation=rotation, retention=retention, compression="zip",
               format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{line} - {message}")
    logger.info("Logging initialized")
