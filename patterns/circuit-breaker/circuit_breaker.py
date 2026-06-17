"""
Circuit Breaker Pattern Implementation
Thread-safe, production-ready implementation
"""

import time
import threading
from enum import Enum
from typing import Callable, Any, Optional
from datetime import datetime, timedelta
from collections import deque


class CircuitState(Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitBreakerError(Exception):
    """Raised ketika circuit breaker dalam state OPEN"""
    pass


class CircuitBreaker:
    def __init__(
        self,
        failure_threshold: int = 5,
        success_threshold: int = 2,
        timeout: int = 60,
        expected_exception: type = Exception
    ):
        self.failure_threshold = failure_threshold
        self.success_threshold = success_threshold
        self.timeout = timeout
        self.expected_exception = expected_exception
        
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: Optional[datetime] = None
        self._lock = threading.Lock()
        self._call_history = deque(maxlen=100)
    
    @property
    def state(self) -> CircuitState:
        return self._state
    
    def call(self, func: Callable, *args, **kwargs) -> Any:
        with self._lock:
            if self._state == CircuitState.OPEN:
                if self._should_attempt_reset():
                    self._state = CircuitState.HALF_OPEN
                    self._success_count = 0
                else:
                    raise CircuitBreakerError(
                        f"Circuit breaker is OPEN. Retry after {self._time_until_retry():.1f}s"
                    )
        
        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except self.expected_exception as e:
            self._on_failure()
            raise e
    
    def _on_success(self):
        with self._lock:
            self._call_history.append(("success", time.time()))
            
            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.success_threshold:
                    self._state = CircuitState.CLOSED
                    self._failure_count = 0
            elif self._state == CircuitState.CLOSED:
                self._failure_count = max(0, self._failure_count - 1)
    
    def _on_failure(self):
        with self._lock:
            self._call_history.append(("failure", time.time()))
            self._failure_count += 1
            self._last_failure_time = datetime.now()
            
            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
            elif self._state == CircuitState.CLOSED:
                if self._failure_count >= self.failure_threshold:
                    self._state = CircuitState.OPEN
    
    def _should_attempt_reset(self) -> bool:
        return (
            self._last_failure_time and
            datetime.now() >= self._last_failure_time + timedelta(seconds=self.timeout)
        )
    
    def _time_until_retry(self) -> float:
        if not self._last_failure_time:
            return 0
        elapsed = (datetime.now() - self._last_failure_time).total_seconds()
        return max(0, self.timeout - elapsed)
    
    def get_metrics(self) -> dict:
        with self._lock:
            recent_calls = [call for call in self._call_history 
                          if time.time() - call[1] < 60]
            total = len(recent_calls)
            failures = sum(1 for call in recent_calls if call[0] == "failure")
            
            return {
                "state": self._state.value,
                "failure_count": self._failure_count,
                "success_count": self._success_count,
                "failure_rate": failures / total if total > 0 else 0,
                "total_calls_last_minute": total
            }


def circuit_breaker(
    failure_threshold: int = 5,
    success_threshold: int = 2,
    timeout: int = 60,
    expected_exception: type = Exception
):
    """Decorator untuk wrap function dengan circuit breaker"""
    cb = CircuitBreaker(
        failure_threshold=failure_threshold,
        success_threshold=success_threshold,
        timeout=timeout,
        expected_exception=expected_exception
    )
    
    def decorator(func):
        def wrapper(*args, **kwargs):
            return cb.call(func, *args, **kwargs)
        wrapper.circuit_breaker = cb
        return wrapper
    return decorator
