# Cache-Aside Pattern - Code Examples

Implementasi lengkap cache-aside pattern dalam Python, Go, dan Node.js.

## Prerequisites

- Docker & Docker Compose
- Python 3.9+ (untuk Python examples)
- Go 1.19+ (untuk Go examples)
- Node.js 16+ (untuk Node.js examples)

## Quick Start

### 1. Start Infrastructure

```bash
docker-compose up -d
```

Ini akan start:
- Redis (port 6379)
- PostgreSQL (port 5432)
- Redis Commander UI (http://localhost:8081)

### 2. Run Python Examples

**Install dependencies:**
```bash
pip install redis psycopg2-binary
```

**Basic example:**
```bash
python cache_aside_basic.py
```

**Advanced example (thundering herd, batch, multi-level):**
```bash
python cache_aside_advanced.py
```

### 3. Run Go Example

**Install dependencies:**
```bash
go mod init cache-aside-demo
go get github.com/go-redis/redis/v8
go get github.com/jackc/pgx/v4
```

**Run:**
```bash
go run cache_aside.go
```

### 4. Run Node.js Example

**Install dependencies:**
```bash
npm install redis pg
```

**Run:**
```bash
node cache_aside.js
```

## Examples Overview

### `cache_aside_basic.py`

Implementasi dasar cache-aside pattern:
- Read with cache check
- Cache miss handling
- Cache invalidation on write
- Negative caching (cache NOT_FOUND results)
- Statistics tracking

**Output:**
```
🚀 Cache-Aside Pattern Demo

Demo 1: First read (cache miss)
✗ Cache MISS: user:profile:1
→ Cached: user:profile:1 (TTL: 3600s)
User: {'id': 1, 'name': 'Alice Johnson', ...}

Demo 2: Second read (cache hit)
✓ Cache HIT: user:profile:1
User: {'id': 1, 'name': 'Alice Johnson', ...}

==================================================
Cache Statistics
==================================================
Hits:       2
Misses:     2
Writes:     1
Hit Rate:   50.00%
==================================================
```

### `cache_aside_advanced.py`

Advanced patterns:

1. **Thundering Herd Protection**
   - Locking mechanism
   - Only 1 thread queries DB for same key
   - Others wait and get cached result

2. **Batch Operations**
   - Batch get from cache (MGET)
   - Batch query DB for misses
   - Batch store to cache (PIPELINE)

3. **Two-Level Cache**
   - L1: Local in-memory cache (fast, small)
   - L2: Distributed Redis cache (shared, large)
   - Automatic cache population

**Run demos:**
```bash
python cache_aside_advanced.py
```

### `cache_aside.go`

Go implementation dengan:
- Type-safe structs
- Context-based operations
- Error handling
- Statistics tracking

### `cache_aside.js`

Node.js implementation dengan:
- Async/await
- Promise-based operations
- Batch operations
- Error handling

## Monitoring

### Redis Commander

Open http://localhost:8081 untuk visual interface ke Redis cache.

Monitor:
- Cached keys
- TTL values
- Memory usage

### Redis CLI

```bash
# Connect
docker exec -it examples_redis_1 redis-cli

# Check stats
INFO stats

# Monitor commands in real-time
MONITOR

# Get all user keys
KEYS user:*

# Check TTL
TTL user:profile:1

# Get hit rate
INFO stats | grep keyspace
```

### PostgreSQL

```bash
# Connect
docker exec -it examples_postgres_1 psql -U postgres -d testdb

# Check slow queries
SELECT * FROM pg_stat_statements 
ORDER BY mean_time DESC 
LIMIT 10;

# Monitor connections
SELECT count(*) FROM pg_stat_activity;
```

## Performance Testing

### Load Test with Apache Bench

```bash
# Install ab
apt-get install apache-bench

# Test endpoint (assuming you have API running)
ab -n 10000 -c 100 http://localhost:8000/users/1
```

### Measure Cache Hit Rate

```python
import time
import random

def benchmark(repo, user_ids, iterations):
    start = time.time()
    
    for _ in range(iterations):
        user_id = random.choice(user_ids)
        repo.get_user(user_id)
    
    elapsed = time.time() - start
    hit_rate = repo.get_hit_rate()
    
    print(f"Iterations: {iterations}")
    print(f"Time: {elapsed:.2f}s")
    print(f"Requests/sec: {iterations/elapsed:.2f}")
    print(f"Hit Rate: {hit_rate:.2f}%")

# Run benchmark
benchmark(repo, [1, 2, 3, 4, 5], 10000)
```

## Common Issues

### Issue: Connection refused to Redis

```bash
# Check if Redis is running
docker ps | grep redis

# Check logs
docker logs examples_redis_1

# Restart
docker-compose restart redis
```

### Issue: PostgreSQL connection failed

```bash
# Check if PostgreSQL is ready
docker exec examples_postgres_1 pg_isready

# Check logs
docker logs examples_postgres_1
```

### Issue: Cache not invalidating

Pastikan TTL di-set dan invalidation logic dipanggil setelah write:

```python
# After DB write
cache.delete(f"user:{user_id}")
```

## Clean Up

```bash
# Stop services
docker-compose down

# Remove volumes (clear data)
docker-compose down -v
```

## Next Steps

1. Implement cache warming strategy
2. Add metrics export (Prometheus)
3. Implement circuit breaker for cache failures
4. Add distributed locking (Redis SETNX)
5. Implement cache versioning
6. Add compression for large objects

## References

- [Redis Documentation](https://redis.io/docs/)
- [PostgreSQL Best Practices](https://www.postgresql.org/docs/)
- Main README: `../README.md`
