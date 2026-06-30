"""
Cache-Aside Pattern - Basic Implementation
==========================================

Contoh implementasi dasar cache-aside pattern dengan Redis dan PostgreSQL.
"""

import redis
import psycopg2
import json
import time
from typing import Optional, Dict, Any
from datetime import datetime


class CacheAsideRepository:
    """Repository dengan cache-aside pattern"""
    
    def __init__(self, redis_client: redis.Redis, db_connection):
        self.cache = redis_client
        self.db = db_connection
        self.default_ttl = 3600  # 1 jam
        self.stats = {
            'hits': 0,
            'misses': 0,
            'writes': 0
        }
    
    def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        """
        Get user by ID dengan cache-aside pattern.
        
        Flow:
        1. Check cache
        2. If miss, query database
        3. Store result in cache
        4. Return data
        """
        cache_key = f"user:profile:{user_id}"
        
        # 1. Try cache first
        cached = self.cache.get(cache_key)
        if cached:
            self.stats['hits'] += 1
            print(f"✓ Cache HIT: {cache_key}")
            return json.loads(cached)
        
        # 2. Cache miss - query database
        self.stats['misses'] += 1
        print(f"✗ Cache MISS: {cache_key}")
        
        cursor = self.db.cursor()
        cursor.execute("""
            SELECT id, name, email, created_at, last_login
            FROM users 
            WHERE id = %s
        """, (user_id,))
        
        row = cursor.fetchone()
        if not row:
            # Cache negative result untuk prevent repeated queries
            self.cache.setex(cache_key, 300, "NOT_FOUND")
            return None
        
        user = {
            'id': row[0],
            'name': row[1],
            'email': row[2],
            'created_at': row[3].isoformat() if row[3] else None,
            'last_login': row[4].isoformat() if row[4] else None
        }
        
        # 3. Store in cache
        self.cache.setex(cache_key, self.default_ttl, json.dumps(user))
        print(f"→ Cached: {cache_key} (TTL: {self.default_ttl}s)")
        
        return user
    
    def update_user(self, user_id: int, name: str, email: str) -> bool:
        """
        Update user dan invalidate cache.
        
        Flow:
        1. Update database (source of truth)
        2. Invalidate cache
        """
        try:
            cursor = self.db.cursor()
            cursor.execute("""
                UPDATE users 
                SET name = %s, email = %s, updated_at = NOW()
                WHERE id = %s
            """, (name, email, user_id))
            
            self.db.commit()
            self.stats['writes'] += 1
            
            # Invalidate cache
            cache_key = f"user:profile:{user_id}"
            deleted = self.cache.delete(cache_key)
            
            if deleted:
                print(f"⊗ Cache INVALIDATED: {cache_key}")
            
            return True
            
        except Exception as e:
            self.db.rollback()
            print(f"✗ Update failed: {e}")
            return False
    
    def delete_user(self, user_id: int) -> bool:
        """Delete user dari DB dan cache"""
        try:
            cursor = self.db.cursor()
            cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
            self.db.commit()
            
            # Invalidate cache
            cache_key = f"user:profile:{user_id}"
            self.cache.delete(cache_key)
            print(f"⊗ User deleted and cache invalidated: {user_id}")
            
            return True
            
        except Exception as e:
            self.db.rollback()
            print(f"✗ Delete failed: {e}")
            return False
    
    def get_hit_rate(self) -> float:
        """Calculate cache hit rate"""
        total = self.stats['hits'] + self.stats['misses']
        if total == 0:
            return 0.0
        return (self.stats['hits'] / total) * 100
    
    def print_stats(self):
        """Print cache statistics"""
        print("\n" + "="*50)
        print("Cache Statistics")
        print("="*50)
        print(f"Hits:       {self.stats['hits']}")
        print(f"Misses:     {self.stats['misses']}")
        print(f"Writes:     {self.stats['writes']}")
        print(f"Hit Rate:   {self.get_hit_rate():.2f}%")
        print("="*50 + "\n")


def demo():
    """Demo cache-aside pattern"""
    
    # Setup connections
    redis_client = redis.Redis(
        host='localhost',
        port=6379,
        decode_responses=True
    )
    
    db_conn = psycopg2.connect(
        "host=localhost dbname=testdb user=postgres password=postgres"
    )
    
    repo = CacheAsideRepository(redis_client, db_conn)
    
    print("\n🚀 Cache-Aside Pattern Demo\n")
    
    # Demo 1: First read - cache miss
    print("Demo 1: First read (cache miss)")
    print("-" * 50)
    user = repo.get_user(1)
    print(f"User: {user}\n")
    
    # Demo 2: Second read - cache hit
    print("Demo 2: Second read (cache hit)")
    print("-" * 50)
    user = repo.get_user(1)
    print(f"User: {user}\n")
    
    # Demo 3: Third read - still cache hit
    print("Demo 3: Third read (still cache hit)")
    print("-" * 50)
    user = repo.get_user(1)
    print(f"User: {user}\n")
    
    # Demo 4: Update user - invalidate cache
    print("Demo 4: Update user (invalidates cache)")
    print("-" * 50)
    repo.update_user(1, "Updated Name", "updated@example.com")
    print()
    
    # Demo 5: Read after update - cache miss (fresh data)
    print("Demo 5: Read after update (cache miss, fresh data)")
    print("-" * 50)
    user = repo.get_user(1)
    print(f"User: {user}\n")
    
    # Demo 6: Read non-existent user
    print("Demo 6: Read non-existent user (negative caching)")
    print("-" * 50)
    user = repo.get_user(99999)
    print(f"User: {user}\n")
    
    # Print statistics
    repo.print_stats()
    
    # Cleanup
    db_conn.close()
    redis_client.close()


if __name__ == "__main__":
    demo()
