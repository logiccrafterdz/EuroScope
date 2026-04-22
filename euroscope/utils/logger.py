"""
Structured Logging for EuroScope

Provides JSON-formatted file logging alongside human-readable console output
using `structlog` for ElasticSearch/Kibana ingestion.
"""

import logging
import sys
import os
import time
import structlog
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import uuid
import threading

_log_context = threading.local()

def get_correlation_id() -> str:
    if not hasattr(_log_context, "correlation_id"):
        _log_context.correlation_id = str(uuid.uuid4())
    return _log_context.correlation_id

def set_correlation_id(cid: str):
    _log_context.correlation_id = cid

def clear_correlation_id():
    if hasattr(_log_context, "correlation_id"):
        del _log_context.correlation_id

def inject_correlation_id(logger, log_method, event_dict):
    event_dict["correlation_id"] = get_correlation_id()
    return event_dict

def setup_structured_logging(level: str = "INFO", log_dir: str = "data/logs"):
    """
    Configure logging with both console and JSON file handlers using structlog.

    Args:
        level: Log level string (DEBUG, INFO, WARNING, ERROR)
        log_dir: Directory for JSON log files
    """
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    root.handlers.clear()

    # structlog configuration
    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)
    shared_processors = [
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.stdlib.ExtraAdder(),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        timestamper,
        inject_correlation_id,
    ]

    structlog.configure(
        processors=shared_processors + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)
    log_file = log_path / f"euroscope_{datetime.now(timezone.utc).strftime('%Y%m%d')}.jsonl"

    formatter_console = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.dev.ConsoleRenderer(colors=True) if os.getenv("EUROSCOPE_JSON_CONSOLE", "0") != "1" else structlog.processors.JSONRenderer(),
        ],
    )
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter_console)
    root.addHandler(console_handler)

    formatter_file = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.JSONRenderer(),
        ],
    )
    file_handler = logging.FileHandler(str(log_file), encoding="utf-8")
    file_handler.setFormatter(formatter_file)
    file_handler.setLevel(logging.DEBUG)  # Always capture everything in file
    root.addHandler(file_handler)

    # Suppress noisy third-party loggers
    for noisy in ("httpx", "httpcore", "yfinance", "telegram", "urllib3", "matplotlib"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    primp_logger = logging.getLogger('primp')
    primp_logger.setLevel(logging.CRITICAL)
    primp_logger.propagate = False
    
    primp_impersonate = logging.getLogger('primp.impersonate')
    primp_impersonate.setLevel(logging.CRITICAL)
    primp_impersonate.propagate = False

    logging.getLogger("euroscope").info(
        f"Structured logging initialized (console={level}, file={log_file})"
    )

def get_logger(name: str) -> logging.Logger:
    """Get a named logger under the euroscope namespace."""
    if not name.startswith("euroscope"):
        name = f"euroscope.{name}"
    return logging.getLogger(name)

@contextmanager
def log_duration(operation: str, logger: logging.Logger = None):
    """
    Context manager that logs the duration of an operation.

    Usage:
        with log_duration("fetch_price", logger):
            price = provider.get_price()
    """
    if logger is None:
        logger = logging.getLogger("euroscope.perf")

    start = time.perf_counter()
    try:
        yield
    finally:
        duration_ms = (time.perf_counter() - start) * 1000
        logger.info(
            f"{operation} completed in {duration_ms:.1f}ms",
            extra={"duration_ms": round(duration_ms, 1), "operation": operation},
        )
