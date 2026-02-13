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
from datetime import datetime
from pathlib import Path


class JSONFormatter(logging.Formatter):
    """Formats log records as JSON lines for structured file logging."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        if record.exc_info and record.exc_info[0]:
            log_entry["exception"] = self.formatException(record.exc_info)
        # Include any extra fields
        for key in ("duration_ms", "operation", "data"):
            if hasattr(record, key):
                log_entry[key] = getattr(record, key)
        return json.dumps(log_entry, ensure_ascii=False)


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
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
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

    # Console handler — human-readable
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(ConsoleFormatter())
    console.setLevel(getattr(logging, level.upper(), logging.INFO))
    root.addHandler(console)

    # File handler — JSON structured
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)
    log_file = log_path / f"euroscope_{datetime.utcnow().strftime('%Y%m%d')}.jsonl"

    file_handler = logging.FileHandler(str(log_file), encoding="utf-8")
    file_handler.setFormatter(JSONFormatter())
    file_handler.setLevel(logging.DEBUG)  # Always capture everything in file
    root.addHandler(file_handler)

    # Suppress noisy third-party loggers
    for noisy in ("httpx", "httpcore", "yfinance", "telegram", "urllib3", "matplotlib"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

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
