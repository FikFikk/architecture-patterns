# Cache-Aside Pattern (Lazy Loading)

## Ringkasan

Cache-Aside adalah strategi caching di mana aplikasi bertanggung jawab mengelola cache secara eksplisit. Data dimuat ke cache hanya ketika dibutuhkan (lazy loading), dan aplikasi yang mengontrol kapan data dibaca dari cache atau database.

Pattern ini juga dikenal sebagai **Lazy Loading** atau **Read-Through Cache** (meskipun ada perbedaan subtle dengan true read-through).

## Problem yang Diselesaikan

### Masalah Umum
1. **Database Overload**: Query yang sama dieksekusi berulang kali, membebani database
2. **High Latency**: Setiap request harus akses storage yang lambat (disk I/O, network latency)
3. **Scalability Bottleneck**: Database menjadi single point of contention saat traffic naik
4. **Cost**: Database premium (managed RDS, DynamoDB) mahal untuk read-heavy workloads

### Skenario Konkrit
- **E-commerce**: Product catalog yang jarang berubah tapi sering dibaca
- **Social Media**: User profiles, follower counts, trending topics
- **News/Content Sites**: Artikel populer yang dibaca ribuan kali
- **API Gateway**: Rate limiting counters, API keys validation
- **Configuration Service**: Application settings yang jarang berubah

## Cara Kerja

### Flow Diagram

```
┌─────────────┐
│ Application │
└──────┬──────┘
       │
       │ 1. Read Request
       ▼
┌─────────────┐
│   Cache     │
│  (Redis/    │
│ Memcached)  │
└──────┬──────┘
       │
       ├─── Cache Hit ──────► Return Data (Fast! ~1ms)
       │
       └─── Cache Miss
              │
              │ 2. Query Database
              ▼
       ┌─────────────┐
       │  Database   │
       │ (Postgres/  │
       │   MySQL)    │
       └──────┬──────┘
              │
              │ 3. Return Data
              ▼
       ┌─────────────┐
       │   Cache     │
       │ 4. Store in │
       │    Cache    │
       └─────────────┘
              │
              │ 5. Return to Client
              ▼
```

### Algoritma

**Read Operation:**
```
function getData(key):
    # 1. Cek cache dulu
    data = cache.get(key)
    
    if data is not None:
        # Cache hit - return langsung
        return data
    
    # 2. Cache miss - query database
    data = database.query(key)
    
    if data is not None:
        # 3. Simpan ke cache untuk request berikutnya
        cache.set(key, data, ttl=3600)  # TTL 1 jam
    
    return data
```

**Write Operation:**
```
function updateData(key, newData):
    # 1. Update database first (source of truth)
    database.update(key, newData)
    
    # 2. Invalidate cache (bukan update langsung)
    cache.delete(key)
    
    # Alternatif: Update cache immediately
    # cache.set(key, newData, ttl=3600)
```

## Implementation

### Python + Redis

```python
import redis
import psycopg2
from typing import Optional
import json

class CacheAsideRepository:
    def __init__(self, redis_client: redis.Redis, db_connection):
        self.cache = redis_client
        self.db = db_connection
        self.default_ttl = 3600  # 1 jam
    
    def get_user(self, user_id: int) -> Optional[dict]:
        """Get user dengan cache-aside pattern"""
        cache_key = f"user:{user_id}"
        
        # 1. Cek cache
        cached = self.cache.get(cache_key)
        if cached:
            print(f"Cache HIT: {cache_key}")
            return json.loads(cached)
        
        print(f"Cache MISS: {cache_key}")
        
        # 2. Query database
        cursor = self.db.cursor()
        cursor.execute(
            "SELECT id, name, email, created_at FROM users WHERE id = %s",
            (user_id,)
        )
        row = cursor.fetchone()
        
        if not row:
            return None
        
        user = {
            'id': row[0],
            'name': row[1],
            'email': row[2],
            'created_at': row[3].isoformat()
        }
        
        # 3. Store di cache
        self.cache.setex(
            cache_key,
            self.default_ttl,
            json.dumps(user)
        )
        
        return user
    
    def update_user(self, user_id: int, name: str, email: str):
        """Update user dan invalidate cache"""
        # 1. Update database (source of truth)
        cursor = self.db.cursor()
        cursor.execute(
            "UPDATE users SET name = %s, email = %s WHERE id = %s",
            (name, email, user_id)
        )
        self.db.commit()
        
        # 2. Invalidate cache
        cache_key = f"user:{user_id}"
        self.cache.delete(cache_key)
        
        print(f"Cache INVALIDATED: {cache_key}")

# Usage
redis_client = redis.Redis(host='localhost', port=6379, decode_responses=True)
db_conn = psycopg2.connect("dbname=myapp user=postgres")

repo = CacheAsideRepository(redis_client, db_conn)

# First call - cache miss, query DB
user = repo.get_user(123)  # Cache MISS: user:123

# Second call - cache hit, no DB query
user = repo.get_user(123)  # Cache HIT: user:123

# Update - invalidate cache
repo.update_user(123, "New Name", "new@email.com")  # Cache INVALIDATED

# Next read - cache miss lagi, data fresh dari DB
user = repo.get_user(123)  # Cache MISS: user:123 (fresh data)
```

### Go Implementation

Lihat file: [`examples/cache-aside.go`](examples/cache-aside.go)

### Node.js Implementation

Lihat file: [`examples/cache-aside.js`](examples/cache-aside.js)

## Trade-offs

### ✅ Kelebihan

1. **Simple & Flexible**
   - Aplikasi punya kontrol penuh kapan cache, kapan tidak
   - Mudah dipahami dan di-debug
   - Tidak butuh infrastructure khusus (cukup Redis/Memcached)

2. **Cache Hanya Data yang Dibutuhkan**
   - Tidak waste memory untuk data yang jarang diakses
   - Cache "warm up" organik seiring traffic

3. **Resilient terhadap Cache Failure**
   - Kalau cache down, aplikasi masih bisa baca dari database (degraded performance, tapi tidak down)
   - Cache bukan critical dependency

4. **Stale Data Acceptable**
   - Untuk use case di mana consistency bisa eventual (product catalogs, analytics)

### ❌ Kekurangan

1. **Cache Miss Penalty**
   - Request pertama selalu lambat (cache miss)
   - Cold start setelah cache eviction atau restart bisa kasih latency spike

2. **Thundering Herd Problem**
   - Jika cache expire untuk key populer, bisa ratusan request simultan hit database
   - Mitigasi: locking mechanism, stale-while-revalidate

3. **Inconsistency Window**
   - Data di cache bisa stale sampai TTL expire atau explicit invalidation
   - Write-heavy workloads bisa susah maintain consistency

4. **Code Complexity**
   - Setiap data access layer perlu logic cache management
   - Lebih banyak code dibanding read-through/write-through otomatis

5. **Cache Invalidation Hell**
   - "There are only two hard things in Computer Science: cache invalidation and naming things"
   - Sulit invalidate cache yang terkait (contoh: user profile vs user posts)

## When to Use

### ✅ Gunakan Cache-Aside Jika:

- **Read-heavy workloads** (read:write ratio > 10:1)
- **Data jarang berubah** (product catalogs, configurations, reference data)
- **Eventual consistency acceptable** (tidak butuh real-time consistency)
- **Predictable access patterns** (hot data jelas, mengikuti power law distribution)
- **Latency critical** (butuh sub-millisecond response time)

### ❌ Hindari Cache-Aside Jika:

- **Write-heavy workloads** - cache akan sering di-invalidate, hit rate rendah
- **Strong consistency required** - financial transactions, inventory counts
- **Data set sangat besar** - memory cache tidak cukup, eviction terlalu agresif
- **Access pattern unpredictable** - random access tanpa locality, cache tidak efektif

## Scalability Considerations

### Horizontal Scaling

**Problem:** Kalau pakai in-memory cache lokal (per-instance), setiap instance punya cache sendiri. Inconsistency antar instance.

**Solution:** Centralized cache layer (Redis Cluster, Memcached).

```
┌──────────┐    ┌──────────┐    ┌──────────┐
│  App     │    │  App     │    │  App     │
│ Instance │    │ Instance │    │ Instance │
│    1     │    │    2     │    │    3     │
└────┬─────┘    └────┬─────┘    └────┬─────┘
     │               │               │
     └───────────────┴───────────────┘
                     │
              ┌──────▼──────┐
              │    Redis    │
              │   Cluster   │
              │ (Shared L2  │
              │   Cache)    │
              └─────────────┘
                     │
              ┌──────▼──────┐
              │  Database   │
              └─────────────┘
```

### Cache Warming

**Problem:** Setelah deploy atau cache restart, semua request cache miss → database overload.

**Solution:**

1. **Pre-populate cache** sebelum terima traffic:
```python
def warm_cache():
    """Warm up cache dengan hot data"""
    popular_user_ids = [1, 2, 5, 10, 42, 100]  # dari analytics
    for user_id in popular_user_ids:
        get_user(user_id)  # populate cache
```

2. **Gradual traffic ramp-up** dengan load balancer

3. **Persistent cache** - gunakan Redis persistence (AOF/RDB) agar cache survive restart

### Thundering Herd Mitigation

**Problem:** Key populer expire, 1000 request simultan hit database.

**Solution 1: Locking**
```python
import threading

class CacheAsideWithLock:
    def __init__(self, cache, db):
        self.cache = cache
        self.db = db
        self.locks = {}  # key -> Lock
        self.locks_lock = threading.Lock()
    
    def get_user(self, user_id):
        cache_key = f"user:{user_id}"
        
        # Cek cache
        cached = self.cache.get(cache_key)
        if cached:
            return json.loads(cached)
        
        # Get or create lock untuk key ini
        with self.locks_lock:
            if cache_key not in self.locks:
                self.locks[cache_key] = threading.Lock()
            lock = self.locks[cache_key]
        
        # Hanya 1 thread yang query DB, yang lain wait
        with lock:
            # Double-check cache (thread lain mungkin sudah populate)
            cached = self.cache.get(cache_key)
            if cached:
                return json.loads(cached)
            
            # Query DB
            user = self._query_db(user_id)
            
            # Store cache
            self.cache.setex(cache_key, 3600, json.dumps(user))
            
            return user
```

**Solution 2: Probabilistic Early Expiration**

Expire cache sebelum TTL habis secara probabilistik, untuk spread regeneration load:

```python
import random
import time

def get_with_early_expiration(key, ttl=3600):
    cached = cache.get(key)
    
    if cached:
        data, timestamp = json.loads(cached)
        age = time.time() - timestamp
        
        # Probabilitas regenerate naik seiring age mendekati TTL
        # P(regenerate) = age / ttl
        if random.random() < (age / ttl):
            # Regenerate in background (asyncio/threading)
            regenerate_async(key)
        
        return data
    
    # Cache miss - normal flow
    data = query_db(key)
    cache.set(key, json.dumps([data, time.time()]), ttl)
    return data
```

### Multi-Level Caching

Kombinasi local in-memory cache (L1) + distributed cache (L2):

```
Request
   │
   ├──► L1 Cache (Local, in-memory, ~0.1ms)
   │        ├─ Hit → Return
   │        └─ Miss ↓
   │
   ├──► L2 Cache (Redis, ~1ms)
   │        ├─ Hit → Store in L1 → Return
   │        └─ Miss ↓
   │
   └──► Database (~10-100ms)
            └─ Store in L2 → Store in L1 → Return
```

**Benefits:**
- L1 eliminates network latency untuk hot data
- L2 share data across instances, mengurangi DB load
- L1 ukuran kecil (LRU eviction), L2 ukuran besar

## Real-World Examples

### 1. **Facebook TAO (The Associations and Objects)**

Facebook menggunakan cache-aside pattern untuk social graph (friendships, likes, comments).

- **L1 Cache**: In-process cache di setiap web server
- **L2 Cache**: Memcached cluster (hundreds of TB)
- **Database**: MySQL shards

**Optimization:**
- Lease mechanism untuk prevent thundering herd
- Write-through untuk hot objects, invalidate untuk cold objects
- Asynchronous invalidation via message queue

**Scale:** Handles trillions of reads/day, 99.8%+ cache hit rate

### 2. **Twitter Timeline Cache**

Timeline generation mahal (merge tweets dari followings, apply filters, rank).

- **Cache Key**: `timeline:user:<user_id>`
- **TTL**: 2-5 menit (short, karena tweets real-time)
- **Invalidation**: Ketika user posts tweet baru, invalidate timeline followers

**Strategy:**
- Pre-compute timeline untuk active users (< 1 hour ago)
- Cache-aside untuk inactive users (on-demand)
- Fallback ke real-time computation kalau cache miss

### 3. **Netflix Content Metadata**

Movie/series metadata (titles, thumbnails, descriptions) jarang berubah tapi dibaca jutaan kali.

- **Cache**: EVCache (custom Memcached wrapper)
- **TTL**: 24 jam
- **Warming**: Pre-populate trending content
- **Multi-region**: Regional cache clusters untuk reduce latency

**Result:** 95%+ cache hit rate, average latency < 1ms

### 4. **Stripe API Rate Limiting**

Rate limit counters (requests per minute per API key) disimpan di Redis.

```python
def check_rate_limit(api_key):
    key = f"ratelimit:{api_key}:{current_minute()}"
    
    count = cache.get(key)
    if count is None:
        cache.setex(key, 60, 1)
        return True  # Allow
    
    if int(count) >= 100:  # 100 req/min limit
        return False  # Deny
    
    cache.incr(key)
    return True
```

- **Pattern**: Cache-aside dengan atomic operations (INCR)
- **TTL**: 60 detik (auto-expire setelah window)
- **Fallback**: Allow request kalau Redis down (fail-open untuk availability)

### 5. **GitHub Repository Metadata**

Repo stars, forks, last commit info di-cache agresif.

- **Cache Key**: `repo:<owner>/<name>:metadata`
- **TTL**: 5 menit untuk active repos, 1 jam untuk archived
- **Invalidation**: On push webhook, invalidate related caches
- **CDN Layer**: Cloudflare cache di depan Redis untuk static content

## Advanced Patterns

### 1. **Cache Versioning**

Gunakan version di cache key untuk instant invalidation tanpa delete:

```python
# Global version number
CACHE_VERSION = "v2"

def get_user(user_id):
    key = f"{CACHE_VERSION}:user:{user_id}"
    # ... cache logic

# Saat schema change, bump version
CACHE_VERSION = "v3"  # Semua cache v2 effectively invalid
```

### 2. **Negative Caching**

Cache "not found" results untuk prevent repeated DB queries:

```python
def get_user(user_id):
    key = f"user:{user_id}"
    cached = cache.get(key)
    
    if cached == "NOT_FOUND":
        return None
    
    if cached:
        return json.loads(cached)
    
    user = db.query(user_id)
    
    if user is None:
        cache.setex(key, 300, "NOT_FOUND")  # Cache 5 menit
    else:
        cache.setex(key, 3600, json.dumps(user))
    
    return user
```

**Use case:** Prevent cache penetration attacks (query non-existent keys repeatedly).

### 3. **Batch Caching**

Optimize multi-key reads dengan pipeline:

```python
def get_users_batch(user_ids):
    keys = [f"user:{uid}" for uid in user_ids]
    
    # 1. Batch get dari cache
    cached_values = cache.mget(keys)
    
    result = {}
    missing_ids = []
    
    for user_id, cached in zip(user_ids, cached_values):
        if cached:
            result[user_id] = json.loads(cached)
        else:
            missing_ids.append(user_id)
    
    # 2. Batch query DB untuk cache misses
    if missing_ids:
        users = db.query_batch(missing_ids)
        
        # 3. Batch store ke cache
        pipeline = cache.pipeline()
        for user in users:
            key = f"user:{user['id']}"
            pipeline.setex(key, 3600, json.dumps(user))
            result[user['id']] = user
        pipeline.execute()
    
    return result
```

## Monitoring & Metrics

### Key Metrics

1. **Cache Hit Rate**
   ```
   Hit Rate = Cache Hits / (Cache Hits + Cache Misses)
   ```
   - Target: > 80% untuk read-heavy workloads
   - < 50% indikasi TTL terlalu pendek atau working set > cache size

2. **Cache Miss Latency**
   - P50, P95, P99 latency saat cache miss
   - Bandingkan dengan cache hit latency (harus 10-100x lebih lambat)

3. **Eviction Rate**
   - Berapa banyak keys di-evict karena memory penuh
   - High eviction rate → perlu scale up cache memory

4. **Cache Memory Usage**
   - Monitor used memory vs max memory
   - Alert kalau > 80% (risiko eviction hot keys)

### Observability

```python
from prometheus_client import Counter, Histogram

cache_hits = Counter('cache_hits_total', 'Cache hits', ['cache_name'])
cache_misses = Counter('cache_misses_total', 'Cache misses', ['cache_name'])
cache_latency = Histogram('cache_latency_seconds', 'Cache operation latency')

def get_user_instrumented(user_id):
    with cache_latency.time():
        cached = cache.get(f"user:{user_id}")
        
        if cached:
            cache_hits.labels(cache_name='user').inc()
            return json.loads(cached)
        
        cache_misses.labels(cache_name='user').inc()
        
        # Query DB...
```

### Redis Monitoring

```bash
# Hit rate dari Redis INFO
redis-cli INFO stats | grep keyspace

# Output:
# keyspace_hits:1000000
# keyspace_misses:50000
# Hit rate = 1000000 / (1000000 + 50000) = 95.2%

# Memory usage
redis-cli INFO memory

# Evictions
redis-cli INFO stats | grep evicted_keys
```

## Common Pitfalls

### 1. **Cache Key Collision**

❌ **Wrong:**
```python
key = f"user:{user_id}"  # Collision kalau ada user:123 dan product:123
```

✅ **Correct:**
```python
key = f"user:profile:{user_id}"
key = f"product:detail:{product_id}"
```

### 2. **Unbounded Cache Growth**

❌ **Wrong:**
```python
cache.set(key, value)  # Tanpa TTL, akan penuh
```

✅ **Correct:**
```python
cache.setex(key, 3600, value)  # Dengan TTL
# Atau set maxmemory-policy di Redis (allkeys-lru)
```

### 3. **Cache Stampede**

Sudah dijelaskan di atas (gunakan locking atau probabilistic expiration).

### 4. **Stale Data After Write**

❌ **Wrong:**
```python
def update_user(user_id, name):
    db.update(user_id, name)
    # Lupa invalidate cache!
```

✅ **Correct:**
```python
def update_user(user_id, name):
    db.update(user_id, name)
    cache.delete(f"user:{user_id}")
```

### 5. **Serialization Overhead**

Large objects (> 1MB) lambat serialize/deserialize. Consider:
- Compress data (gzip, snappy)
- Store hanya field yang diperlukan
- Split ke multiple cache keys

## Comparison dengan Cache Patterns Lain

| Pattern | Who Manages Cache | Read Flow | Write Flow | Complexity |
|---------|-------------------|-----------|------------|------------|
| **Cache-Aside** | Application | App checks cache → DB → App updates cache | App writes DB → App invalidates cache | Medium |
| **Read-Through** | Cache layer | App → Cache (auto-loads from DB if miss) | App writes DB → Cache invalidated | Low |
| **Write-Through** | Cache layer | Same as read-through | App → Cache → DB (sync write) | Low |
| **Write-Behind** | Cache layer | Same as read-through | App → Cache → DB (async write) | High |

**Cache-Aside** paling fleksibel tapi butuh aplikasi manage logic explicitly. Read/Write-Through lebih simple tapi kurang kontrol.

## Referensi dan Further Reading

### Papers & Articles

1. **"Scaling Memcache at Facebook"** - Facebook Engineering
   - https://research.facebook.com/publications/scaling-memcache-at-facebook/
   - Deep dive TAO architecture dan cache strategies

2. **"Caching at Netflix: A Modern Approach"** - Netflix Tech Blog
   - https://netflixtechblog.com/
   - EVCache design dan multi-region caching

3. **"The Architecture of Open Source Applications - Memcached"**
   - http://aosabook.org/en/memcached.html

### Books

1. **"Designing Data-Intensive Applications"** - Martin Kleppmann
   - Chapter 3: Storage and Retrieval (caching strategies)

2. **"High Performance Browser Networking"** - Ilya Grigorik
   - HTTP caching dan CDN patterns

3. **"Release It! Design and Deploy Production-Ready Software"** - Michael Nygard
   - Circuit breakers dan caching untuk resilience

### Tools & Technologies

- **Redis**: https://redis.io/docs/manual/client-side-caching/
- **Memcached**: https://github.com/memcached/memcached/wiki
- **Caffeine** (Java in-memory cache): https://github.com/ben-manes/caffeine
- **Hazelcast** (distributed cache): https://hazelcast.com/
- **AWS ElastiCache**: https://aws.amazon.com/elasticache/

### Related Patterns

- **Circuit Breaker**: Fallback kalau cache atau DB down
- **Bulkhead**: Isolate cache pool dari main thread pool
- **Rate Limiting**: Gunakan cache untuk counter
- **CQRS**: Cache untuk read model
- **Event Sourcing**: Cache untuk materialized views

---

**Pattern ini cocok untuk mayoritas aplikasi web modern. Start simple, measure hit rate, optimize later.**
