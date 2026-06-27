import time
import math
from typing import Dict, Tuple, Any, Optional

class TokenBucket:
    """
    Algoritma Token Bucket.
    Menampung token hingga capacity.
    Token ditambahkan kembali pada kelajuan refill_rate (token/detik).
    Sangat cocok untuk menangani burst traffic.
    """
    def __init__(self, capacity: int, refill_rate: float):
        self.capacity = float(capacity)
        self.refill_rate = float(refill_rate)
        self.tokens = float(capacity)
        self.last_refill = time.time()

    def allow_request(self, tokens_requested: int = 1) -> Tuple[bool, Dict[str, Any]]:
        now = time.time()
        elapsed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
        self.last_refill = now

        allowed = False
        if self.tokens >= tokens_requested:
            self.tokens -= tokens_requested
            allowed = True

        retry_after = 0.0
        if not allowed:
            needed = tokens_requested - self.tokens
            retry_after = needed / self.refill_rate

        metadata = {
            "allowed": allowed,
            "remaining_tokens": int(self.tokens),
            "capacity": int(self.capacity),
            "retry_after_seconds": round(retry_after, 2)
        }
        return allowed, metadata


class SlidingWindowCounter:
    """
    Algoritma Sliding Window Counter.
    Menghitung jumlah request dalam jendela waktu bergerak (sliding window).
    Mencegah spike di batas jendela (boundary condition fix).
    """
    def __init__(self, window_size_seconds: int, max_requests: int):
        self.window_size = float(window_size_seconds)
        self.max_requests = max_requests
        self.current_window_start = int(time.time() // window_size_seconds) * window_size_seconds
        self.previous_window_count = 0
        self.current_window_count = 0

    def allow_request(self) -> Tuple[bool, Dict[str, Any]]:
        now = time.time()
        current_window = int(now // self.window_size) * self.window_size

        if current_window > self.current_window_start:
            if current_window == self.current_window_start + self.window_size:
                self.previous_window_count = self.current_window_count
            else:
                self.previous_window_count = 0
            self.current_window_count = 0
            self.current_window_start = current_window

        time_into_current_window = now - self.current_window_start
        weight = (self.window_size - time_into_current_window) / self.window_size
        estimated_count = self.previous_window_count * weight + self.current_window_count

        allowed = False
        if estimated_count + 1 <= self.max_requests:
            self.current_window_count += 1
            allowed = True
            estimated_count += 1

        remaining = max(0, int(self.max_requests - estimated_count))
        metadata = {
            "allowed": allowed,
            "estimated_current_requests": round(estimated_count, 2),
            "max_requests": self.max_requests,
            "remaining_requests": remaining
        }
        return allowed, metadata


class RateLimiterManager:
    """
    Manajer multi-tenant rate limiting berdasarkan Client ID / IP Address.
    """
    def __init__(self, default_capacity: int = 10, default_refill_rate: float = 2.0):
        self.default_capacity = default_capacity
        self.default_refill_rate = default_refill_rate
        self.limiters: Dict[str, TokenBucket] = {}

    def get_limiter(self, client_id: str) -> TokenBucket:
        if client_id not in self.limiters:
            self.limiters[client_id] = TokenBucket(self.default_capacity, self.default_refill_rate)
        return self.limiters[client_id]

    def process_request(self, client_id: str) -> Tuple[bool, Dict[str, Any]]:
        limiter = self.get_limiter(client_id)
        return limiter.allow_request()
