"""
Circuit Breaker Pattern Implementation

Provides fault tolerance for external service calls (databases, APIs, etc.)
by failing fast when a service is unhealthy, and gradually recovering.

States:
- CLOSED: Normal operation, requests pass through
- OPEN: Service is down, requests fail immediately
- HALF_OPEN: Testing if service has recovered
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from functools import wraps
from typing import Any, Callable, Optional, TypeVar, Union

from src.utils.logger import logger

T = TypeVar('T')


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing fast
    HALF_OPEN = "half_open"  # Testing recovery


class CircuitBreakerError(Exception):
    """Raised when circuit breaker is open and request is rejected."""
    
    def __init__(self, message: str, retry_after: float = 0):
        super().__init__(message)
        self.retry_after = retry_after


class CircuitBreakerOpenError(CircuitBreakerError):
    """Raised when circuit is open and not accepting requests."""
    pass


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker behavior."""
    # Number of failures before opening circuit
    failure_threshold: int = 5
    # Seconds to wait before trying again (half-open state)
    recovery_timeout: float = 30.0
    # Number of successful calls in half-open before closing
    success_threshold: int = 2
    # Exceptions to count as failures (None = all)
    failure_exceptions: Optional[tuple] = None
    # Name for logging
    name: str = "default"


@dataclass
class CircuitBreakerStats:
    """Statistics for monitoring circuit breaker."""
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    rejected_calls: int = 0
    last_failure_time: Optional[float] = None
    last_success_time: Optional[float] = None
    consecutive_failures: int = 0
    consecutive_successes: int = 0


class CircuitBreaker:
    """
    Circuit breaker implementation for fault tolerance.
    
    Usage:
        breaker = CircuitBreaker(CircuitBreakerConfig(
            failure_threshold=5,
            recovery_timeout=30.0,
            name="database"
        ))
        
        # Sync usage
        result = await breaker.call(some_async_function, arg1, arg2)
        
        # Or as decorator
        @breaker.protect
        async def my_function():
            ...
    """
    
    def __init__(self, config: Optional[CircuitBreakerConfig] = None):
        self.config = config or CircuitBreakerConfig()
        self._state = CircuitState.CLOSED
        self._stats = CircuitBreakerStats()
        self._lock = asyncio.Lock()
    
    @property
    def state(self) -> CircuitState:
        """Current circuit state."""
        return self._state
    
    @property
    def stats(self) -> CircuitBreakerStats:
        """Current statistics."""
        return self._stats
    
    @property
    def is_closed(self) -> bool:
        """True if circuit is closed (normal operation)."""
        return self._state == CircuitState.CLOSED
    
    @property
    def is_open(self) -> bool:
        """True if circuit is open (failing fast)."""
        return self._state == CircuitState.OPEN
    
    @property
    def is_half_open(self) -> bool:
        """True if circuit is half-open (testing recovery)."""
        return self._state == CircuitState.HALF_OPEN
    
    def _should_allow_request(self) -> bool:
        """Check if a request should be allowed through."""
        if self._state == CircuitState.CLOSED:
            return True
        
        if self._state == CircuitState.OPEN:
            # Check if recovery timeout has passed
            if self._stats.last_failure_time:
                elapsed = time.time() - self._stats.last_failure_time
                if elapsed >= self.config.recovery_timeout:
                    # Transition to half-open
                    self._state = CircuitState.HALF_OPEN
                    logger.info(
                        f"[CircuitBreaker:{self.config.name}] Transitioning to HALF_OPEN "
                        f"after {elapsed:.1f}s"
                    )
                    return True
            return False
        
        # HALF_OPEN - allow limited requests through
        return True
    
    def _on_success(self) -> None:
        """Handle successful call."""
        self._stats.total_calls += 1
        self._stats.successful_calls += 1
        self._stats.last_success_time = time.time()
        self._stats.consecutive_successes += 1
        self._stats.consecutive_failures = 0
        
        if self._state == CircuitState.HALF_OPEN:
            if self._stats.consecutive_successes >= self.config.success_threshold:
                # Recovery successful, close circuit
                self._state = CircuitState.CLOSED
                logger.info(
                    f"[CircuitBreaker:{self.config.name}] Circuit CLOSED after "
                    f"{self._stats.consecutive_successes} successful calls"
                )
    
    def _on_failure(self, error: Exception) -> None:
        """Handle failed call."""
        self._stats.total_calls += 1
        self._stats.failed_calls += 1
        self._stats.last_failure_time = time.time()
        self._stats.consecutive_failures += 1
        self._stats.consecutive_successes = 0
        
        if self._state == CircuitState.HALF_OPEN:
            # Recovery failed, back to open
            self._state = CircuitState.OPEN
            logger.warning(
                f"[CircuitBreaker:{self.config.name}] Circuit OPEN (recovery failed): {error}"
            )
        elif self._state == CircuitState.CLOSED:
            if self._stats.consecutive_failures >= self.config.failure_threshold:
                # Too many failures, open circuit
                self._state = CircuitState.OPEN
                logger.error(
                    f"[CircuitBreaker:{self.config.name}] Circuit OPEN after "
                    f"{self._stats.consecutive_failures} consecutive failures: {error}"
                )
    
    def _is_failure_exception(self, error: Exception) -> bool:
        """Check if exception should be counted as a failure."""
        if self.config.failure_exceptions is None:
            return True
        return isinstance(error, self.config.failure_exceptions)
    
    async def call(self, func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        """
        Execute a function through the circuit breaker.
        
        Args:
            func: Async function to call
            *args: Positional arguments for func
            **kwargs: Keyword arguments for func
            
        Returns:
            Result of func
            
        Raises:
            CircuitBreakerOpenError: If circuit is open
            Original exception: If func fails
        """
        async with self._lock:
            if not self._should_allow_request():
                self._stats.rejected_calls += 1
                retry_after = self.config.recovery_timeout
                if self._stats.last_failure_time:
                    elapsed = time.time() - self._stats.last_failure_time
                    retry_after = max(0, self.config.recovery_timeout - elapsed)
                
                raise CircuitBreakerOpenError(
                    f"Circuit breaker '{self.config.name}' is OPEN. "
                    f"Service temporarily unavailable.",
                    retry_after=retry_after
                )
        
        try:
            # Execute the function
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)
            
            async with self._lock:
                self._on_success()
            
            return result
            
        except Exception as e:
            async with self._lock:
                if self._is_failure_exception(e):
                    self._on_failure(e)
            raise
    
    def protect(self, func: Callable[..., T]) -> Callable[..., T]:
        """
        Decorator to protect a function with the circuit breaker.
        
        Usage:
            @breaker.protect
            async def my_function():
                ...
        """
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            return await self.call(func, *args, **kwargs)
        return wrapper
    
    def reset(self) -> None:
        """Reset circuit breaker to initial state."""
        self._state = CircuitState.CLOSED
        self._stats = CircuitBreakerStats()
        logger.info(f"[CircuitBreaker:{self.config.name}] Reset to CLOSED")
    
    def get_status(self) -> dict:
        """Get current status for monitoring/health checks."""
        return {
            "name": self.config.name,
            "state": self._state.value,
            "stats": {
                "total_calls": self._stats.total_calls,
                "successful_calls": self._stats.successful_calls,
                "failed_calls": self._stats.failed_calls,
                "rejected_calls": self._stats.rejected_calls,
                "consecutive_failures": self._stats.consecutive_failures,
                "consecutive_successes": self._stats.consecutive_successes,
            },
            "config": {
                "failure_threshold": self.config.failure_threshold,
                "recovery_timeout": self.config.recovery_timeout,
                "success_threshold": self.config.success_threshold,
            }
        }


# Pre-configured circuit breakers for common services
_circuit_breakers: dict[str, CircuitBreaker] = {}


def get_circuit_breaker(
    name: str,
    failure_threshold: int = 5,
    recovery_timeout: float = 30.0,
    success_threshold: int = 2,
) -> CircuitBreaker:
    """
    Get or create a named circuit breaker.
    
    Args:
        name: Unique name for the circuit breaker
        failure_threshold: Failures before opening
        recovery_timeout: Seconds before trying again
        success_threshold: Successes needed to close
        
    Returns:
        CircuitBreaker instance (cached by name)
    """
    if name not in _circuit_breakers:
        _circuit_breakers[name] = CircuitBreaker(
            CircuitBreakerConfig(
                name=name,
                failure_threshold=failure_threshold,
                recovery_timeout=recovery_timeout,
                success_threshold=success_threshold,
            )
        )
    return _circuit_breakers[name]


def get_all_circuit_breaker_status() -> dict[str, dict]:
    """Get status of all circuit breakers for monitoring."""
    return {name: cb.get_status() for name, cb in _circuit_breakers.items()}


# Common circuit breakers
database_breaker = get_circuit_breaker(
    "database",
    failure_threshold=5,
    recovery_timeout=30.0,
    success_threshold=2,
)

checkpointer_breaker = get_circuit_breaker(
    "checkpointer", 
    failure_threshold=3,
    recovery_timeout=60.0,  # Longer timeout for persistent storage
    success_threshold=1,
)

external_api_breaker = get_circuit_breaker(
    "external_api",
    failure_threshold=10,
    recovery_timeout=15.0,
    success_threshold=3,
)

