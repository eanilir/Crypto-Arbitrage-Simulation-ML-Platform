from __future__ import annotations

import logging
from typing import Any

LOGGER_NAME = "data_collector"


def get_collector_logger(exchange: str) -> logging.Logger:
    return logging.getLogger(f"{LOGGER_NAME}.{exchange}")


def log_event(logger: logging.Logger, event: str, **fields: Any) -> None:
    parts = [f"{key}={value}" for key, value in sorted(fields.items())]
    details = " ".join(parts)
    logger.info("collector_event=%s %s", event, details)
