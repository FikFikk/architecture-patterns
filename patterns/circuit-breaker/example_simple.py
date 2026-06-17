"""
Example: Simple Usage dengan Decorator
"""

import time
import requests
from circuit_breaker import circuit_breaker, CircuitBreakerError


# Example 1: Decorator usage
@circuit_breaker(
    failure_threshold=3,
    timeout=30,
    expected_exception=requests.RequestException
)
def call_external_api(endpoint: str):
    """Call external API dengan circuit breaker protection"""
    response = requests.get(endpoint, timeout=5)
    response.raise_for_status()
    return response.json()


# Example 2: Dengan fallback
@circuit_breaker(failure_threshold=3, timeout=30)
def get_user_profile(user_id: str):
    """Fetch user profile dari external service"""
    response = requests.get(f"https://api.example.com/users/{user_id}", timeout=5)
    response.raise_for_status()
    return response.json()


def get_user_with_fallback(user_id: str):
    """Wrapper dengan fallback ke cache"""
    try:
        return get_user_profile(user_id)
    except CircuitBreakerError:
        # Fallback: return cached data
        print(f"Circuit open, using cached data for user {user_id}")
        return get_cached_user(user_id)
    except requests.RequestException as e:
        print(f"Request failed: {e}")
        return None


def get_cached_user(user_id: str):
    """Fallback: get from cache"""
    return {
        "id": user_id,
        "name": "Cached User",
        "email": "cached@example.com",
        "cached": True
    }


# Example 3: Monitoring metrics
def monitor_circuit_breaker():
    """Monitor circuit breaker status"""
    metrics = call_external_api.circuit_breaker.get_metrics()
    print(f"Circuit Breaker Metrics:")
    print(f"  State: {metrics['state']}")
    print(f"  Failure Count: {metrics['failure_count']}")
    print(f"  Failure Rate: {metrics['failure_rate']:.2%}")
    print(f"  Total Calls (last minute): {metrics['total_calls_last_minute']}")
    return metrics


if __name__ == "__main__":
    # Demo: Simulate failures and recovery
    print("=== Circuit Breaker Demo ===")
    
    # Simulate multiple failures
    print("
1. Simulating failures...")
    for i in range(5):
        try:
            result = call_external_api("https://httpbin.org/delay/10")
        except Exception as e:
            print(f"  Attempt {i+1}: {type(e).__name__}")
        time.sleep(0.5)
    
    # Check state
    print("
2. Checking circuit breaker state...")
    monitor_circuit_breaker()
    
    # Try to call when circuit is open
    print("
3. Trying to call when circuit is open...")
    try:
        call_external_api("https://httpbin.org/get")
    except CircuitBreakerError as e:
        print(f"  Circuit is OPEN: {e}")
    
    # Wait for timeout and recovery
    print("
4. Waiting for timeout period...")
    time.sleep(31)
    
    print("
5. Trying again after timeout (HALF-OPEN)...")
    try:
        result = call_external_api("https://httpbin.org/get")
        print(f"  Success! Circuit recovered.")
    except Exception as e:
        print(f"  Still failing: {e}")
    
    # Final state
    print("
6. Final circuit breaker state:")
    monitor_circuit_breaker()
