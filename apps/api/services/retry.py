"""
Retry Policy Service

Provides retry logic with exponential backoff for worker tasks.
"""
import time
import functools
from typing import Callable, Any, Optional
from dataclasses import dataclass


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""
    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 30.0
    exponential_base: float = 2.0
    retryable_errors: tuple = (
        "engine unavailable",
        "connection refused",
        "timeout",
        "comfyui offline",
        "ollama offline",
    )


class RetryableError(Exception):
    """Error that should trigger a retry."""
    pass


class NonRetryableError(Exception):
    """Error that should NOT trigger a retry."""
    pass


def is_retryable(error: Exception, config: RetryConfig) -> bool:
    """Check if an error should be retried."""
    error_str = str(error).lower()
    
    for pattern in config.retryable_errors:
        if pattern in error_str:
            return True
    
    # Specific exception types
    if isinstance(error, (TimeoutError, ConnectionError, RetryableError)):
        return True
    
    return False


def calculate_delay(attempt: int, config: RetryConfig) -> float:
    """Calculate delay for exponential backoff."""
    delay = config.base_delay * (config.exponential_base ** attempt)
    return min(delay, config.max_delay)


def with_retry(
    config: Optional[RetryConfig] = None,
    on_retry: Optional[Callable[[Exception, int], None]] = None,
):
    """
    Decorator that adds retry logic with exponential backoff.
    
    Usage:
        @with_retry(RetryConfig(max_retries=3))
        def my_task():
            ...
    """
    config = config or RetryConfig()
    
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            last_error = None
            
            for attempt in range(config.max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_error = e
                    
                    # Don't retry non-retryable errors
                    if isinstance(e, NonRetryableError):
                        raise
                    
                    if not is_retryable(e, config):
                        raise
                    
                    # Last attempt - raise
                    if attempt >= config.max_retries:
                        raise
                    
                    # Calculate delay and wait
                    delay = calculate_delay(attempt, config)
                    
                    if on_retry:
                        on_retry(e, attempt + 1)
                    
                    time.sleep(delay)
            
            # Should not reach here
            raise last_error
        
        return wrapper
    return decorator


def retry_once_on_bad_output(func: Callable) -> Callable:
    """
    Decorator that retries once if function returns None or empty.
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs) -> Any:
        result = func(*args, **kwargs)
        
        if result is None or result == "" or result == []:
            # Retry once
            result = func(*args, **kwargs)
        
        return result
    
    return wrapper


# Pre-configured policies
COMFYUI_RETRY = RetryConfig(
    max_retries=3,
    base_delay=2.0,
    max_delay=60.0,
    retryable_errors=(
        "engine unavailable",
        "comfyui offline",
        "connection refused",
        "workflow failed",
    ),
)

OLLAMA_RETRY = RetryConfig(
    max_retries=3,
    base_delay=1.0,
    max_delay=30.0,
    retryable_errors=(
        "ollama offline",
        "connection refused",
        "model not found",
    ),
)

FFMPEG_RETRY = RetryConfig(
    max_retries=1,
    base_delay=0.5,
    max_delay=5.0,
    retryable_errors=(
        "timeout",
        "resource busy",
    ),
)
