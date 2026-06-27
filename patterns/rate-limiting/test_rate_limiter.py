import time
import unittest
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from rate_limiter import TokenBucket, SlidingWindowCounter, RateLimiterManager

class TestRateLimiter(unittest.TestCase):

    def test_token_bucket_burst_and_refill(self):
        limiter = TokenBucket(capacity=3, refill_rate=2.0)
        
        ok1, meta1 = limiter.allow_request()
        ok2, meta2 = limiter.allow_request()
        ok3, meta3 = limiter.allow_request()
        
        self.assertTrue(ok1)
        self.assertTrue(ok2)
        self.assertTrue(ok3)
        self.assertEqual(meta3["remaining_tokens"], 0)
        
        ok4, meta4 = limiter.allow_request()
        self.assertFalse(ok4)
        self.assertGreater(meta4["retry_after_seconds"], 0.0)
        
        time.sleep(0.6)
        ok5, meta5 = limiter.allow_request()
        self.assertTrue(ok5)

    def test_sliding_window_counter(self):
        limiter = SlidingWindowCounter(window_size_seconds=1, max_requests=2)
        
        ok1, meta1 = limiter.allow_request()
        ok2, meta2 = limiter.allow_request()
        ok3, meta3 = limiter.allow_request()
        
        self.assertTrue(ok1)
        self.assertTrue(ok2)
        self.assertFalse(ok3)
        
        # Sleep for full window to clear previous window weight
        time.sleep(2.0)
        ok4, meta4 = limiter.allow_request()
        self.assertTrue(ok4)

    def test_rate_limiter_manager_isolation(self):
        manager = RateLimiterManager(default_capacity=2, default_refill_rate=1.0)
        
        self.assertTrue(manager.process_request("client_a")[0])
        self.assertTrue(manager.process_request("client_a")[0])
        self.assertFalse(manager.process_request("client_a")[0])
        
        self.assertTrue(manager.process_request("client_b")[0])
        self.assertTrue(manager.process_request("client_b")[0])
        self.assertFalse(manager.process_request("client_b")[0])

if __name__ == "__main__":
    unittest.main()
