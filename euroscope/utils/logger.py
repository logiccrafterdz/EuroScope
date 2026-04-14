"""
Structured Logging for EuroScope

Provides JSON-formatted file logging alongside human-readable console output.
Includes a performance timing context manager for profiling operations.
"""

import json
import logging
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


from pythonjsonlogger import jsonlogger
import uuid
import threading

# Thread-local storage for correlation IDs
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

class CorrelationIdFilter(logging.Filter):
    """Injects a correlation_id into all log records."""
    def filter(self, record):
        record.correlation_id = get_correlation_id()
        return True

class CustomJsonFormatter(jsonlogger.JsonFormatter):
    """Extended JSON formatter with UTC injection and required fields."""
    def add_fields(self, log_record, record, message_dict):
        super().add_fields(log_record, record, message_dict)
        if not log_record.get('timestamp'):
            now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%fZ')
            log_record['timestamp'] = now
        if log_record.get('level'):
            log_record['level'] = log_record['level'].upper()
        else:
            log_record['level'] = record.levelname
        log_record['logger'] = record.name
        log_record['module'] = record.module
        log_record['function'] = record.funcName
        log_record['line'] = record.lineno


class ConsoleFormatter(logging.Formatter):
    """Human-readable colored console formatter."""

    COLORS = {
        "DEBUG": "\033[36m",     # Cyan
        "INFO": "\033[32m",      # Green
        "WARNING": "\033[33m",   # Yellow
        "ERROR": "\033[31m",     # Red
        "CRITICAL": "\033[1;31m",  # Bold Red
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelname, self.RESET)
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        msg = record.getMessage()
        base = f"{timestamp} │ {color}{record.levelname:<7}{self.RESET} │ {record.name:<28} │ {msg}"

        if record.exc_info and record.exc_info[0]:
            base += "\n" + self.formatException(record.exc_info)
        return base


def setup_structured_logging(level: str = "INFO", log_dir: str = "data/logs"):
    """
    Configure logging with both console and JSON file handlers.

    Args:
        level: Log level string (DEBUG, INFO, WARNING, ERROR)
        log_dir: Directory for JSON log files
    """
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Clear existing handlers to prevent duplicates on re-init
    root.handlers.clear()

    # Console handler — human-readable or JSON
    import os
    console = logging.StreamHandler(sys.stdout)
    if os.getenv("EUROSCOPE_JSON_CONSOLE", "0") == "1":
        console.setFormatter(CustomJsonFormatter('%(timestamp)s %(level)s %(name)s %(message)s'))
    else:
        console.setFormatter(ConsoleFormatter())
    console.setLevel(getattr(logging, level.upper(), logging.INFO))
    console.addFilter(CorrelationIdFilter())
    root.addHandler(console)

    # File handler — JSON structured
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)
    log_file = log_path / f"euroscope_{datetime.now(timezone.utc).strftime('%Y%m%d')}.jsonl"

    file_handler = logging.FileHandler(str(log_file), encoding="utf-8")
    file_handler.setFormatter(CustomJsonFormatter('%(timestamp)s %(level)s %(correlation_id)s %(name)s %(message)s'))
    file_handler.setLevel(logging.DEBUG)  # Always capture everything in file
    file_handler.addFilter(CorrelationIdFilter())
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
