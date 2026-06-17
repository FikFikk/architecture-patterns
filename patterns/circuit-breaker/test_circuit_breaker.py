"""
Unit Tests untuk Circuit Breaker Pattern
"""

import time
import pytest
from unittest.mock import Mock
from circuit_breaker import CircuitBreaker, CircuitState, CircuitBreakerError


def test_circuit_starts_closed():
    breaker = CircuitBreaker(failure_threshold=3)
    assert breaker.state == CircuitState.CLOSED


def test_circuit_opens_after_threshold():
    breaker = CircuitBreaker(failure_threshold=3, timeout=60)
    failing_func = Mock(side_effect=Exception("Service down"))
    
    # Trigger failures
    for _ in range(3):
        with pytest.raises(Exception):
            breaker.call(failing_func)
    
    # Circuit should be OPEN
    assert breaker.state == CircuitState.OPEN
    
    # Next call should raise CircuitBreakerError
    with pytest.raises(CircuitBreakerError):
        breaker.call(failing_func)


def test_circuit_stays_closed_below_threshold():
    breaker = CircuitBreaker(failure_threshold=5)
    failing_func = Mock(side_effect=Exception("Error"))
    
    # Fail 4 times (below threshold)
    for _ in range(4):
        with pytest.raises(Exception):
            breaker.call(failing_func)
    
    # Should still be CLOSED
    assert breaker.state == CircuitState.CLOSED


def test_half_open_transition():
    breaker = CircuitBreaker(
        failure_threshold=2,
        success_threshold=2,
        timeout=1
    )
    
    # Open circuit
    failing_func = Mock(side_effect=Exception("Down"))
    for _ in range(2):
        with pytest.raises(Exception):
            breaker.call(failing_func)
    
    assert breaker.state == CircuitState.OPEN
    
    # Wait for timeout
    time.sleep(1.1)
    
    # Next call should transition to HALF_OPEN
    success_func = Mock(return_value="OK")
    result = breaker.call(success_func)
    assert result == "OK"
    assert breaker.state == CircuitState.HALF_OPEN


def test_half_open_to_closed():
    breaker = CircuitBreaker(
        failure_threshold=2,
        success_threshold=2,
        timeout=1
    )
    
    # Open circuit
    failing_func = Mock(side_effect=Exception("Down"))
    for _ in range(2):
        with pytest.raises(Exception):
            breaker.call(failing_func)
    
    time.sleep(1.1)
    
    # Success calls should close circuit
    success_func = Mock(return_value="OK")
    breaker.call(success_func)
    assert breaker.state == CircuitState.HALF_OPEN
    
    breaker.call(success_func)
    assert breaker.state == CircuitState.CLOSED


def test_half_open_to_open_on_failure():
    breaker = CircuitBreaker(
        failure_threshold=2,
        success_threshold=2,
        timeout=1
    )
    
    # Open circuit
    failing_func = Mock(side_effect=Exception("Down"))
    for _ in range(2):
        with pytest.raises(Exception):
            breaker.call(failing_func)
    
    time.sleep(1.1)
    
    # Fail in HALF_OPEN should go back to OPEN
    with pytest.raises(Exception):
        breaker.call(failing_func)
    
    assert breaker.state == CircuitState.OPEN


def test_metrics_tracking():
    breaker = CircuitBreaker(failure_threshold=5)
    success_func = Mock(return_value="OK")
    failing_func = Mock(side_effect=Exception("Error"))
    
    # Mix of success and failure
    breaker.call(success_func)
    breaker.call(success_func)
    
    try:
        breaker.call(failing_func)
    except:
        pass
    
    metrics = breaker.get_metrics()
    assert metrics["state"] == "CLOSED"
    assert metrics["failure_count"] == 1
    assert metrics["total_calls_last_minute"] == 3


def test_success_decrements_failure_count():
    breaker = CircuitBreaker(failure_threshold=5)
    failing_func = Mock(side_effect=Exception("Error"))
    success_func = Mock(return_value="OK")
    
    # Some failures
    for _ in range(3):
        with pytest.raises(Exception):
            breaker.call(failing_func)
    
    assert breaker._failure_count == 3
    
    # Success should decrement
    breaker.call(success_func)
    assert breaker._failure_count == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
