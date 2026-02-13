"""
Resilience Utilities — Retry decorators for transient API errors.

Prevents the bot from crashing on temporary network failures,
API rate limits, or connection timeouts.
"""

import functools
import logging
import time
from typing import Callable, Type

logger = logging.getLogger("euroscope.utils.resilience")


def retry(max_attempts: int = 3, delay: float = 1.0,
          backoff: float = 2.0,
          exceptions: tuple[Type[Exception], ...] = (Exception,)):
    """
    Retry decorator with exponential backoff.

    Args:
        max_attempts: Maximum number of retry attempts
        delay: Initial delay between retries (seconds)
        backoff: Multiplier for delay after each retry
        exceptions: Tuple of exception types to catch

    Usage:
        @retry(max_attempts=3, exceptions=(ConnectionError, TimeoutError))
        def fetch_price():
            ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            current_delay = delay
            last_exception = None

            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_attempts:
                        logger.warning(
                            f"[Retry {attempt}/{max_attempts}] "
                            f"{func.__name__} failed: {e}. "
                            f"Retrying in {current_delay:.1f}s..."
                        )
                        time.sleep(current_delay)
                        current_delay *= backoff
                    else:
                        logger.error(
                            f"[Retry {attempt}/{max_attempts}] "
                            f"{func.__name__} failed permanently: {e}"
                        )

            raise last_exception

        return wrapper
    return decorator


def safe_call(func: Callable, *args, default=None, **kwargs):
    """
    Call a function safely, returning default on any exception.

    Usage:
        price = safe_call(provider.get_price, default={"error": "unavailable"})
    """
    try:
        return func(*args, **kwargs)
    except Exception as e:
        logger.warning(f"safe_call({func.__name__}) failed: {e}")
        return default


def async_retry(max_attempts: int = 3, delay: float = 1.0,
                backoff: float = 2.0,
                exceptions: tuple[type[Exception], ...] = (Exception,)):
    """
    Async retry decorator with exponential backoff.

    Same as retry() but uses asyncio.sleep() to avoid
    blocking the event loop.

    Usage:
        @async_retry(max_attempts=3, exceptions=(ConnectionError,))
        async def fetch_data():
            ...
    """
    import asyncio

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            current_delay = delay
            last_exception = None

            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_attempts:
                        logger.warning(
                            f"[AsyncRetry {attempt}/{max_attempts}] "
                            f"{func.__name__} failed: {e}. "
                            f"Retrying in {current_delay:.1f}s..."
                        )
                        await asyncio.sleep(current_delay)
                        current_delay *= backoff
                    else:
                        logger.error(
                            f"[AsyncRetry {attempt}/{max_attempts}] "
                            f"{func.__name__} failed permanently: {e}"
                        )

            raise last_exception

        return wrapper
    return decorator
