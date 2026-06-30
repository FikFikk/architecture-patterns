/**
 * Cache-Aside Pattern - Node.js Implementation
 * =============================================
 */

const redis = require('redis');
const { Pool } = require('pg');

class CacheAsideRepository {
  constructor(redisClient, pgPool) {
    this.cache = redisClient;
    this.db = pgPool;
    this.defaultTTL = 3600; // 1 hour
    this.stats = {
      hits: 0,
      misses: 0,
      writes: 0
    };
  }

  /**
   * Get user with cache-aside pattern
   */
  async getUser(userId) {
    const cacheKey = `user:profile:${userId}`;

    try {
      // 1. Check cache first
      const cached = await this.cache.get(cacheKey);
      
      if (cached) {
        this.stats.hits++;
        console.log(`✓ Cache HIT: ${cacheKey}`);
        
        if (cached === 'NOT_FOUND') {
          return null;
        }
        
        return JSON.parse(cached);
      }

      // 2. Cache miss - query database
      this.stats.misses++;
      console.log(`✗ Cache MISS: ${cacheKey}`);

      const result = await this.db.query(
        'SELECT id, name, email, created_at, last_login FROM users WHERE id = $1',
        [userId]
      );

      if (result.rows.length === 0) {
        // Cache negative result
        await this.cache.setEx(cacheKey, 300, 'NOT_FOUND');
        return null;
      }

      const user = result.rows[0];

      // 3. Store in cache
      await this.cache.setEx(cacheKey, this.defaultTTL, JSON.stringify(user));
      console.log(`→ Cached: ${cacheKey} (TTL: ${this.defaultTTL}s)`);

      return user;

    } catch (error) {
      console.error('Error in getUser:', error);
      throw error;
    }
  }

  /**
   * Update user and invalidate cache
   */
  async updateUser(userId, name, email) {
    try {
      // 1. Update database (source of truth)
      await this.db.query(
        'UPDATE users SET name = $1, email = $2, updated_at = NOW() WHERE id = $3',
        [name, email, userId]
      );

      this.stats.writes++;

      // 2. Invalidate cache
      const cacheKey = `user:profile:${userId}`;
      const deleted = await this.cache.del(cacheKey);

      if (deleted > 0) {
        console.log(`⊗ Cache INVALIDATED: ${cacheKey}`);
      }

      return true;

    } catch (error) {
      console.error('Error in updateUser:', error);
      throw error;
    }
  }

  /**
   * Batch get users (optimized)
   */
  async getUsersBatch(userIds) {
    const keys = userIds.map(id => `user:profile:${id}`);

    // 1. Batch get from cache
    const cachedValues = await Promise.all(
      keys.map(key => this.cache.get(key))
    );

    const result = {};
    const missingIds = [];

    userIds.forEach((userId, index) => {
      const cached = cachedValues[index];
      
      if (cached && cached !== 'NOT_FOUND') {
        result[userId] = JSON.parse(cached);
        this.stats.hits++;
      } else {
        missingIds.push(userId);
        this.stats.misses++;
      }
    });

    // 2. Batch query database for cache misses
    if (missingIds.length > 0) {
      const dbResult = await this.db.query(
        'SELECT id, name, email, created_at FROM users WHERE id = ANY($1)',
        [missingIds]
      );

      // 3. Batch store to cache
      const cachePromises = [];
      
      for (const user of dbResult.rows) {
        const cacheKey = `user:profile:${user.id}`;
        result[user.id] = user;
        
        cachePromises.push(
          this.cache.setEx(cacheKey, this.defaultTTL, JSON.stringify(user))
        );
      }

      await Promise.all(cachePromises);
    }

    return result;
  }

  /**
   * Calculate cache hit rate
   */
  getHitRate() {
    const total = this.stats.hits + this.stats.misses;
    return total === 0 ? 0 : (this.stats.hits / total) * 100;
  }

  /**
   * Print cache statistics
   */
  printStats() {
    console.log('\n' + '='.repeat(50));
    console.log('Cache Statistics');
    console.log('='.repeat(50));
    console.log(`Hits:       ${this.stats.hits}`);
    console.log(`Misses:     ${this.stats.misses}`);
    console.log(`Writes:     ${this.stats.writes}`);
    console.log(`Hit Rate:   ${this.getHitRate().toFixed(2)}%`);
    console.log('='.repeat(50) + '\n');
  }
}

// Demo function
async function demo() {
  // Setup connections
  const redisClient = redis.createClient({
    url: 'redis://localhost:6379'
  });
  
  await redisClient.connect();

  const pgPool = new Pool({
    host: 'localhost',
    database: 'testdb',
    user: 'postgres',
    password: 'postgres',
    port: 5432
  });

  const repo = new CacheAsideRepository(redisClient, pgPool);

  console.log('\n🚀 Cache-Aside Pattern Demo (Node.js)\n');

  try {
    // Demo 1: First read - cache miss
    console.log('Demo 1: First read (cache miss)');
    console.log('-'.repeat(50));
    let user = await repo.getUser(1);
    console.log('User:', user);
    console.log();

    // Demo 2: Second read - cache hit
    console.log('Demo 2: Second read (cache hit)');
    console.log('-'.repeat(50));
    user = await repo.getUser(1);
    console.log('User:', user);
    console.log();

    // Demo 3: Third read - still cache hit
    console.log('Demo 3: Third read (still cache hit)');
    console.log('-'.repeat(50));
    user = await repo.getUser(1);
    console.log('User:', user);
    console.log();

    // Demo 4: Update - invalidate cache
    console.log('Demo 4: Update user (invalidates cache)');
    console.log('-'.repeat(50));
    await repo.updateUser(1, 'Updated Name', 'updated@example.com');
    console.log();

    // Demo 5: Read after update - cache miss
    console.log('Demo 5: Read after update (cache miss, fresh data)');
    console.log('-'.repeat(50));
    user = await repo.getUser(1);
    console.log('User:', user);
    console.log();

    // Demo 6: Batch operations
    console.log('Demo 6: Batch get users');
    console.log('-'.repeat(50));
    const users = await repo.getUsersBatch([1, 2, 3, 4, 5]);
    console.log(`Got ${Object.keys(users).length} users`);
    console.log();

    // Print statistics
    repo.printStats();

  } finally {
    await redisClient.quit();
    await pgPool.end();
  }
}

// Run demo
if (require.main === module) {
  demo().catch(console.error);
}

module.exports = { CacheAsideRepository };
