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

class CircuitBreakerOpenException(Exception):
    """Raised when the circuit breaker is open to fail fast."""
    pass

class AsyncCircuitBreaker:
    """
    Asynchronous Circuit Breaker state machine.
    Transitions to OPEN state and fails fast after consecutive failures,
    then allows half-open probes after a timeout.
    """
    def __init__(self, exceptions=(Exception,), failure_threshold=3, recovery_timeout=60.0):
        self.exceptions = exceptions
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = 0.0
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
        
    def _update_state(self):
        if self.state == "OPEN":
            if time.time() - self.last_failure_time > self.recovery_timeout:
                self.state = "HALF_OPEN"
                logger.info("Circuit breaker transitioning from OPEN ➔ HALF_OPEN. Probing...")
                
    async def call(self, func, *args, **kwargs):
        self._update_state()
        
        if self.state == "OPEN":
            raise CircuitBreakerOpenException(f"Circuit breaker is OPEN. Fast failing call to {func.__name__}")
            
        try:
            result = await func(*args, **kwargs)
            
            if self.state == "HALF_OPEN":
                logger.info(f"Circuit breaker probe succeeded! Transitioning HALF_OPEN ➔ CLOSED.")
                self.state = "CLOSED"
                self.failure_count = 0
                
            return result
            
        except self.exceptions as e:
            self.failure_count += 1
            self.last_failure_time = time.time()
            
            if self.state == "HALF_OPEN" or self.failure_count >= self.failure_threshold:
                if self.state != "OPEN":
                    logger.critical(f"Circuit breaker tripped OPEN after {self.failure_count} failures! Outage on {func.__name__}")
                self.state = "OPEN"
                
            raise e

