// Cache-Aside Pattern - Go Implementation
// ========================================

package main

import (
	"context"
	"encoding/json"
	"fmt"
	"time"

	"github.com/go-redis/redis/v8"
	"github.com/jackc/pgx/v4"
)

var ctx = context.Background()

// User represents user data
type User struct {
	ID        int       `json:"id"`
	Name      string    `json:"name"`
	Email     string    `json:"email"`
	CreatedAt time.Time `json:"created_at"`
}

// CacheAsideRepo implements cache-aside pattern
type CacheAsideRepo struct {
	cache      *redis.Client
	db         *pgx.Conn
	defaultTTL time.Duration
	stats      Stats
}

// Stats tracks cache performance
type Stats struct {
	Hits   int64
	Misses int64
	Writes int64
}

// NewCacheAsideRepo creates new repository
func NewCacheAsideRepo(redisClient *redis.Client, dbConn *pgx.Conn) *CacheAsideRepo {
	return &CacheAsideRepo{
		cache:      redisClient,
		db:         dbConn,
		defaultTTL: 1 * time.Hour,
	}
}

// GetUser retrieves user with cache-aside pattern
func (r *CacheAsideRepo) GetUser(userID int) (*User, error) {
	cacheKey := fmt.Sprintf("user:profile:%d", userID)

	// 1. Check cache first
	cached, err := r.cache.Get(ctx, cacheKey).Result()
	if err == nil {
		r.stats.Hits++
		fmt.Printf("✓ Cache HIT: %s\n", cacheKey)

		if cached == "NOT_FOUND" {
			return nil, nil
		}

		var user User
		if err := json.Unmarshal([]byte(cached), &user); err != nil {
			return nil, err
		}
		return &user, nil
	}

	// 2. Cache miss - query database
	r.stats.Misses++
	fmt.Printf("✗ Cache MISS: %s\n", cacheKey)

	var user User
	err = r.db.QueryRow(ctx, `
		SELECT id, name, email, created_at
		FROM users
		WHERE id = $1
	`, userID).Scan(&user.ID, &user.Name, &user.Email, &user.CreatedAt)

	if err == pgx.ErrNoRows {
		// Cache negative result
		r.cache.Set(ctx, cacheKey, "NOT_FOUND", 5*time.Minute)
		return nil, nil
	}
	if err != nil {
		return nil, err
	}

	// 3. Store in cache
	userData, _ := json.Marshal(user)
	r.cache.Set(ctx, cacheKey, userData, r.defaultTTL)
	fmt.Printf("→ Cached: %s (TTL: %v)\n", cacheKey, r.defaultTTL)

	return &user, nil
}

// UpdateUser updates user and invalidates cache
func (r *CacheAsideRepo) UpdateUser(userID int, name, email string) error {
	// 1. Update database
	_, err := r.db.Exec(ctx, `
		UPDATE users
		SET name = $1, email = $2, updated_at = NOW()
		WHERE id = $3
	`, name, email, userID)

	if err != nil {
		return err
	}

	r.stats.Writes++

	// 2. Invalidate cache
	cacheKey := fmt.Sprintf("user:profile:%d", userID)
	deleted, _ := r.cache.Del(ctx, cacheKey).Result()
	if deleted > 0 {
		fmt.Printf("⊗ Cache INVALIDATED: %s\n", cacheKey)
	}

	return nil
}

// GetHitRate calculates cache hit rate
func (r *CacheAsideRepo) GetHitRate() float64 {
	total := r.stats.Hits + r.stats.Misses
	if total == 0 {
		return 0
	}
	return float64(r.stats.Hits) / float64(total) * 100
}

// PrintStats prints cache statistics
func (r *CacheAsideRepo) PrintStats() {
	fmt.Println("\n" + "="*50)
	fmt.Println("Cache Statistics")
	fmt.Println("="*50)
	fmt.Printf("Hits:       %d\n", r.stats.Hits)
	fmt.Printf("Misses:     %d\n", r.stats.Misses)
	fmt.Printf("Writes:     %d\n", r.stats.Writes)
	fmt.Printf("Hit Rate:   %.2f%%\n", r.GetHitRate())
	fmt.Println("="*50)
}

func main() {
	// Setup Redis connection
	rdb := redis.NewClient(&redis.Options{
		Addr: "localhost:6379",
		DB:   0,
	})
	defer rdb.Close()

	// Setup PostgreSQL connection
	conn, err := pgx.Connect(ctx, "postgres://postgres:postgres@localhost:5432/testdb")
	if err != nil {
		panic(err)
	}
	defer conn.Close(ctx)

	repo := NewCacheAsideRepo(rdb, conn)

	fmt.Println("\n🚀 Cache-Aside Pattern Demo (Go)\n")

	// Demo 1: First read - cache miss
	fmt.Println("Demo 1: First read (cache miss)")
	fmt.Println("-" + "-"*49)
	user, _ := repo.GetUser(1)
	fmt.Printf("User: %+v\n\n", user)

	// Demo 2: Second read - cache hit
	fmt.Println("Demo 2: Second read (cache hit)")
	fmt.Println("-" + "-"*49)
	user, _ = repo.GetUser(1)
	fmt.Printf("User: %+v\n\n", user)

	// Demo 3: Update - invalidate cache
	fmt.Println("Demo 3: Update user (invalidates cache)")
	fmt.Println("-" + "-"*49)
	repo.UpdateUser(1, "Updated Name", "updated@example.com")
	fmt.Println()

	// Demo 4: Read after update - cache miss
	fmt.Println("Demo 4: Read after update (cache miss, fresh data)")
	fmt.Println("-" + "-"*49)
	user, _ = repo.GetUser(1)
	fmt.Printf("User: %+v\n\n", user)

	repo.PrintStats()
}
