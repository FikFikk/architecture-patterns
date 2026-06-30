"""
Cache-Aside Pattern - Advanced Implementation
==============================================

Implementasi advanced dengan:
- Thundering herd protection (locking)
- Batch operations
- Multi-level caching
- Metrics/observability
"""

import redis
import threading
import time
import json
from typing import List, Dict, Optional, Any
from collections import defaultdict
from datetime import datetime


class AdvancedCacheAside:
    """Cache-aside dengan thundering herd protection"""
    
    def __init__(self, cache: redis.Redis, default_ttl: int = 3600):
        self.cache = cache
        self.default_ttl = default_ttl
        
        # Locking untuk prevent thundering herd
        self.locks = {}
        self.locks_lock = threading.Lock()
        
        # Metrics
        self.metrics = defaultdict(int)
    
    def get_with_lock(self, key: str, fetch_fn, ttl: Optional[int] = None):
        """
        Get data dengan thundering herd protection.
        
        Jika cache miss, hanya 1 thread yang execute fetch_fn.
        Thread lain wait dan dapat hasil dari thread pertama.
        """
        ttl = ttl or self.default_ttl
        
        # Try cache first
        cached = self.cache.get(key)
        if cached:
            self.metrics['hits'] += 1
            return json.loads(cached) if cached != "NOT_FOUND" else None
        
        self.metrics['misses'] += 1
        
        # Get or create lock for this key
        with self.locks_lock:
            if key not in self.locks:
                self.locks[key] = threading.Lock()
            lock = self.locks[key]
        
        # Only 1 thread executes fetch, others wait
        with lock:
            # Double-check cache (another thread might have populated it)
            cached = self.cache.get(key)
            if cached:
                self.metrics['lock_avoided'] += 1
                return json.loads(cached) if cached != "NOT_FOUND" else None
            
            # Fetch data
            self.metrics['fetches'] += 1
            data = fetch_fn()
            
            # Cache result (including None/not found)
            if data is None:
                self.cache.setex(key, 300, "NOT_FOUND")
            else:
                self.cache.setex(key, ttl, json.dumps(data))
            
            return data
    
    def get_batch(self, keys: List[str], fetch_fn) -> Dict[str, Any]:
        """
        Batch get dengan automatic cache population untuk misses.
        
        Args:
            keys: List of cache keys
            fetch_fn: Function(missing_keys) -> Dict[key, value]
        """
        if not keys:
            return {}
        
        # 1. Batch get from cache
        cached_values = self.cache.mget(keys)
        
        result = {}
        missing_keys = []
        
        for key, cached in zip(keys, cached_values):
            if cached and cached != "NOT_FOUND":
                result[key] = json.loads(cached)
                self.metrics['hits'] += 1
            else:
                missing_keys.append(key)
                self.metrics['misses'] += 1
        
        # 2. Fetch missing data
        if missing_keys:
            fetched_data = fetch_fn(missing_keys)
            
            # 3. Batch store to cache
            if fetched_data:
                pipeline = self.cache.pipeline()
                for key, value in fetched_data.items():
                    pipeline.setex(key, self.default_ttl, json.dumps(value))
                    result[key] = value
                pipeline.execute()
                self.metrics['batch_fetches'] += 1
        
        return result
    
    def invalidate(self, key: str) -> bool:
        """Invalidate single key"""
        deleted = self.cache.delete(key)
        if deleted:
            self.metrics['invalidations'] += 1
        return bool(deleted)
    
    def invalidate_pattern(self, pattern: str) -> int:
        """Invalidate multiple keys matching pattern"""
        keys = list(self.cache.scan_iter(match=pattern))
        if keys:
            deleted = self.cache.delete(*keys)
            self.metrics['invalidations'] += deleted
            return deleted
        return 0
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get cache metrics"""
        total = self.metrics['hits'] + self.metrics['misses']
        hit_rate = (self.metrics['hits'] / total * 100) if total > 0 else 0
        
        return {
            'hits': self.metrics['hits'],
            'misses': self.metrics['misses'],
            'hit_rate': f"{hit_rate:.2f}%",
            'fetches': self.metrics['fetches'],
            'batch_fetches': self.metrics['batch_fetches'],
            'lock_avoided': self.metrics['lock_avoided'],
            'invalidations': self.metrics['invalidations']
        }


class TwoLevelCache:
    """
    Multi-level cache: L1 (in-memory) + L2 (Redis)
    
    L1: Fast, local, small (LRU)
    L2: Shared across instances, larger
    """
    
    def __init__(self, redis_client: redis.Redis, l1_size: int = 1000):
        self.l2 = redis_client
        self.l1 = {}  # Simple dict as L1 (production: use LRU cache)
        self.l1_size = l1_size
        self.l1_access = {}  # Track access time for LRU
        
        self.metrics = {
            'l1_hits': 0,
            'l2_hits': 0,
            'misses': 0
        }
    
    def get(self, key: str, fetch_fn, ttl: int = 3600) -> Any:
        """Get with 2-level cache"""
        
        # L1 cache check
        if key in self.l1:
            self.metrics['l1_hits'] += 1
            self.l1_access[key] = time.time()
            return self.l1[key]
        
        # L2 cache check
        cached = self.l2.get(key)
        if cached:
            self.metrics['l2_hits'] += 1
            data = json.loads(cached) if cached != "NOT_FOUND" else None
            
            # Populate L1
            self._set_l1(key, data)
            return data
        
        # Cache miss - fetch data
        self.metrics['misses'] += 1
        data = fetch_fn()
        
        # Store in both levels
        if data is None:
            self.l2.setex(key, 300, "NOT_FOUND")
        else:
            self.l2.setex(key, ttl, json.dumps(data))
            self._set_l1(key, data)
        
        return data
    
    def _set_l1(self, key: str, value: Any):
        """Set L1 cache with LRU eviction"""
        # Evict if full
        if len(self.l1) >= self.l1_size:
            # Remove least recently used
            lru_key = min(self.l1_access.keys(), key=lambda k: self.l1_access[k])
            del self.l1[lru_key]
            del self.l1_access[lru_key]
        
        self.l1[key] = value
        self.l1_access[key] = time.time()
    
    def invalidate(self, key: str):
        """Invalidate from both levels"""
        if key in self.l1:
            del self.l1[key]
            del self.l1_access[key]
        self.l2.delete(key)
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get cache metrics"""
        total = self.metrics['l1_hits'] + self.metrics['l2_hits'] + self.metrics['misses']
        
        return {
            'l1_hits': self.metrics['l1_hits'],
            'l2_hits': self.metrics['l2_hits'],
            'misses': self.metrics['misses'],
            'total_hits': self.metrics['l1_hits'] + self.metrics['l2_hits'],
            'hit_rate': f"{((self.metrics['l1_hits'] + self.metrics['l2_hits']) / total * 100):.2f}%" if total > 0 else "0%",
            'l1_size': len(self.l1)
        }


def demo_thundering_herd():
    """Demo thundering herd protection"""
    print("\n🔒 Demo: Thundering Herd Protection\n")
    print("Simulasi 10 concurrent requests untuk key yang sama (cache cold)")
    print("-" * 60)
    
    redis_client = redis.Redis(host='localhost', port=6379, decode_responses=True)
    cache = AdvancedCacheAside(redis_client)
    
    # Clear cache
    redis_client.delete("expensive:computation")
    
    fetch_count = {'count': 0}
    
    def expensive_fetch():
        """Simulasi expensive database query"""
        fetch_count['count'] += 1
        print(f"  → Executing expensive fetch (#{fetch_count['count']})...")
        time.sleep(0.5)  # Simulate slow query
        return {'result': 'expensive data', 'timestamp': time.time()}
    
    # 10 concurrent threads requesting same key
    threads = []
    results = []
    
    def worker():
        result = cache.get_with_lock("expensive:computation", expensive_fetch)
        results.append(result)
    
    start = time.time()
    for _ in range(10):
        t = threading.Thread(target=worker)
        threads.append(t)
        t.start()
    
    for t in threads:
        t.join()
    
    elapsed = time.time() - start
    
    print(f"\n✓ Completed in {elapsed:.2f}s")
    print(f"  Fetch executed: {fetch_count['count']} time(s) (tanpa lock: 10 kali)")
    print(f"  {10 - fetch_count['count']} threads waited on lock")
    print(f"\nMetrics: {cache.get_metrics()}")


def demo_batch_operations():
    """Demo batch cache operations"""
    print("\n📦 Demo: Batch Operations\n")
    print("-" * 60)
    
    redis_client = redis.Redis(host='localhost', port=6379, decode_responses=True)
    cache = AdvancedCacheAside(redis_client)
    
    # Clear cache
    for i in range(1, 11):
        redis_client.delete(f"user:{i}")
    
    def fetch_users_batch(keys: List[str]) -> Dict[str, Any]:
        """Simulasi batch DB query"""
        user_ids = [int(k.split(':')[1]) for k in keys]
        print(f"  → Batch fetching {len(user_ids)} users from DB...")
        time.sleep(0.2)
        
        return {
            f"user:{uid}": {'id': uid, 'name': f'User{uid}'}
            for uid in user_ids
        }
    
    # Request 10 users (all cache miss)
    user_keys = [f"user:{i}" for i in range(1, 11)]
    
    print("First batch request (all cache miss):")
    start = time.time()
    users = cache.get_batch(user_keys, fetch_users_batch)
    elapsed = time.time() - start
    print(f"  ✓ Got {len(users)} users in {elapsed:.3f}s\n")
    
    # Request 10 users again (all cache hit)
    print("Second batch request (all cache hit):")
    start = time.time()
    users = cache.get_batch(user_keys, fetch_users_batch)
    elapsed = time.time() - start
    print(f"  ✓ Got {len(users)} users in {elapsed:.3f}s (much faster!)\n")
    
    print(f"Metrics: {cache.get_metrics()}")


def demo_two_level_cache():
    """Demo multi-level caching"""
    print("\n🏢 Demo: Two-Level Cache (L1 + L2)\n")
    print("-" * 60)
    
    redis_client = redis.Redis(host='localhost', port=6379, decode_responses=True)
    cache = TwoLevelCache(redis_client, l1_size=5)
    
    redis_client.flushdb()
    
    def fetch_user(user_id):
        def _fetch():
            print(f"  → Fetching user {user_id} from DB (SLOW)")
            time.sleep(0.1)
            return {'id': user_id, 'name': f'User{user_id}'}
        return _fetch
    
    print("Access pattern: 1, 2, 3, 1 (observe L1 hit), 4, 5, 6, 7, 8 (L1 eviction), 1 (L2 hit)")
    print()
    
    for user_id in [1, 2, 3, 1, 4, 5, 6, 7, 8, 1]:
        user = cache.get(f"user:{user_id}", fetch_user(user_id))
        metrics = cache.get_metrics()
        print(f"  User {user_id}: L1={metrics['l1_hits']} L2={metrics['l2_hits']} Miss={metrics['misses']}")
        time.sleep(0.05)
    
    print(f"\nFinal Metrics: {cache.get_metrics()}")


if __name__ == "__main__":
    demo_thundering_herd()
    print("\n" + "="*60 + "\n")
    demo_batch_operations()
    print("\n" + "="*60 + "\n")
    demo_two_level_cache()
