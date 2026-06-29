package main

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"net/http/httputil"
	"net/url"
	"strings"
	"sync"
	"time"

	"github.com/golang-jwt/jwt/v5"
	"github.com/redis/go-redis/v9"
)

// Service Registry
var services = map[string]string{
	"users":    "http://user-service:3001",
	"orders":   "http://order-service:3002",
	"products": "http://product-service:3003",
	"payments": "http://payment-service:3004",
}

var (
	jwtSecret = []byte("your-secret-key-change-in-production")
	redisClient *redis.Client
	ctx = context.Background()
)

// Rate Limiter dengan sliding window
type RateLimiter struct {
	mu sync.RWMutex
	limits map[string][]time.Time
	tiers map[string]RateLimit
}

type RateLimit struct {
	Requests int
	Window   time.Duration
}

func NewRateLimiter() *RateLimiter {
	return &RateLimiter{
		limits: make(map[string][]time.Time),
		tiers: map[string]RateLimit{
			"free":       {Requests: 100, Window: 15 * time.Minute},
			"basic":      {Requests: 1000, Window: 15 * time.Minute},
			"premium":    {Requests: 10000, Window: 15 * time.Minute},
			"enterprise": {Requests: 100000, Window: 15 * time.Minute},
		},
	}
}

func (rl *RateLimiter) Allow(userID, tier string) bool {
	rl.mu.Lock()
	defer rl.mu.Unlock()

	limit, ok := rl.tiers[tier]
	if !ok {
		limit = rl.tiers["free"]
	}

	now := time.Now()
	key := fmt.Sprintf("%s:%s", userID, tier)

	// Get timestamps untuk user ini
	timestamps := rl.limits[key]

	// Filter timestamps dalam window
	var validTimestamps []time.Time
	for _, ts := range timestamps {
		if now.Sub(ts) < limit.Window {
			validTimestamps = append(validTimestamps, ts)
		}
	}

	// Check limit
	if len(validTimestamps) >= limit.Requests {
		return false
	}

	// Add current timestamp
	validTimestamps = append(validTimestamps, now)
	rl.limits[key] = validTimestamps

	return true
}

// JWT Claims
type Claims struct {
	UserID string `json:"user_id"`
	Tier   string `json:"tier"`
	jwt.RegisteredClaims
}

// Middleware: Logging
func loggingMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()
		log.Printf("[%s] %s %s", time.Now().Format(time.RFC3339), r.Method, r.URL.Path)
		
		next.ServeHTTP(w, r)
		
		duration := time.Since(start)
		log.Printf("  └─ Completed in %v", duration)
	})
}

// Middleware: CORS
func corsMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Access-Control-Allow-Origin", "*")
		w.Header().Set("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
		w.Header().Set("Access-Control-Allow-Headers", "Content-Type, Authorization")

		if r.Method == "OPTIONS" {
			w.WriteHeader(http.StatusOK)
			return
		}

		next.ServeHTTP(w, r)
	})
}

// Middleware: Authentication
func authMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		authHeader := r.Header.Get("Authorization")
		if authHeader == "" {
			http.Error(w, `{"error":"Authorization header required"}`, http.StatusUnauthorized)
			return
		}

		tokenString := strings.TrimPrefix(authHeader, "Bearer ")
		
		claims := &Claims{}
		token, err := jwt.ParseWithClaims(tokenString, claims, func(token *jwt.Token) (interface{}, error) {
			return jwtSecret, nil
		})

		if err != nil || !token.Valid {
			http.Error(w, `{"error":"Invalid token"}`, http.StatusForbidden)
			return
		}

		// Add user info ke context
		ctx := context.WithValue(r.Context(), "user_id", claims.UserID)
		ctx = context.WithValue(ctx, "tier", claims.Tier)
		
		next.ServeHTTP(w, r.WithContext(ctx))
	})
}

// Middleware: Rate Limiting
var rateLimiter = NewRateLimiter()

func rateLimitMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		userID := r.Context().Value("user_id").(string)
		tier := r.Context().Value("tier").(string)

		if !rateLimiter.Allow(userID, tier) {
			w.Header().Set("Retry-After", "900")
			http.Error(w, `{"error":"Rate limit exceeded"}`, http.StatusTooManyRequests)
			return
		}

		next.ServeHTTP(w, r)
	})
}

// Cache dengan Redis
func getCached(key string) ([]byte, error) {
	return redisClient.Get(ctx, key).Bytes()
}

func setCache(key string, value []byte, ttl time.Duration) error {
	return redisClient.Set(ctx, key, value, ttl).Err()
}

// Proxy Handler dengan Caching
func proxyHandler(w http.ResponseWriter, r *http.Request) {
	// Parse URL: /api/{service}/{path}
	parts := strings.SplitN(strings.TrimPrefix(r.URL.Path, "/api/"), "/", 2)
	if len(parts) < 2 {
		http.Error(w, `{"error":"Invalid API path"}`, http.StatusBadRequest)
		return
	}

	serviceName := parts[0]
	path := parts[1]

	// Get service URL
	serviceURL, ok := services[serviceName]
	if !ok {
		http.Error(w, fmt.Sprintf(`{"error":"Service %s not found"}`, serviceName), http.StatusNotFound)
		return
	}

	// Check cache untuk GET requests
	if r.Method == "GET" {
		cacheKey := fmt.Sprintf("cache:%s:%s", serviceName, r.URL.String())
		if cached, err := getCached(cacheKey); err == nil {
			w.Header().Set("Content-Type", "application/json")
			w.Header().Set("X-Cache", "HIT")
			w.Write(cached)
			return
		}
	}

	// Forward request
	target, _ := url.Parse(serviceURL)
	proxy := httputil.NewSingleHostReverseProxy(target)

	// Modify request
	originalDirector := proxy.Director
	proxy.Director = func(req *http.Request) {
		originalDirector(req)
		req.URL.Path = "/" + path
		req.Host = target.Host

		// Add custom headers
		if userID := r.Context().Value("user_id"); userID != nil {
			req.Header.Set("X-User-Id", userID.(string))
		}
		req.Header.Set("X-Request-Id", fmt.Sprintf("%d", time.Now().UnixNano()))
	}

	// Modify response untuk caching
	if r.Method == "GET" {
		proxy.ModifyResponse = func(resp *http.Response) error {
			if resp.StatusCode == http.StatusOK {
				// Read body
				body, err := io.ReadAll(resp.Body)
				if err != nil {
					return err
				}
				resp.Body.Close()

				// Cache response
				cacheKey := fmt.Sprintf("cache:%s:%s", serviceName, r.URL.String())
				setCache(cacheKey, body, 5*time.Minute)

				// Restore body
				resp.Body = io.NopCloser(strings.NewReader(string(body)))
				resp.Header.Set("X-Cache", "MISS")
			}
			return nil
		}
	}

	proxy.ServeHTTP(w, r)
}

// Login Handler
func loginHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != "POST" {
		http.Error(w, `{"error":"Method not allowed"}`, http.StatusMethodNotAllowed)
		return
	}

	var credentials struct {
		Username string `json:"username"`
		Password string `json:"password"`
	}

	if err := json.NewDecoder(r.Body).Decode(&credentials); err != nil {
		http.Error(w, `{"error":"Invalid JSON"}`, http.StatusBadRequest)
		return
	}

	// Mock validation (ganti dengan real auth)
	if credentials.Username == "" || credentials.Password == "" {
		http.Error(w, `{"error":"Username and password required"}`, http.StatusBadRequest)
		return
	}

	// Generate JWT
	expirationTime := time.Now().Add(1 * time.Hour)
	claims := &Claims{
		UserID: "user123",
		Tier:   "free",
		RegisteredClaims: jwt.RegisteredClaims{
			ExpiresAt: jwt.NewNumericDate(expirationTime),
			IssuedAt:  jwt.NewNumericDate(time.Now()),
		},
	}

	token := jwt.NewWithClaims(jwt.SigningMethodHS256, claims)
	tokenString, err := token.SignedString(jwtSecret)
	if err != nil {
		http.Error(w, `{"error":"Failed to generate token"}`, http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]interface{}{
		"access_token": tokenString,
		"token_type":   "bearer",
		"expires_in":   3600,
	})
}

// Dashboard Aggregation Handler
func dashboardHandler(w http.ResponseWriter, r *http.Request) {
	userID := r.Context().Value("user_id").(string)

	// Parallel requests ke multiple services
	type result struct {
		key  string
		data interface{}
		err  error
	}

	results := make(chan result, 3)
	var wg sync.WaitGroup

	// Fetch user profile
	wg.Add(1)
	go func() {
		defer wg.Done()
		resp, err := http.Get(fmt.Sprintf("%s/profile/%s", services["users"], userID))
		if err != nil {
			results <- result{key: "user", err: err}
			return
		}
		defer resp.Body.Close()

		var data interface{}
		json.NewDecoder(resp.Body).Decode(&data)
		results <- result{key: "user", data: data}
	}()

	// Fetch recent orders
	wg.Add(1)
	go func() {
		defer wg.Done()
		resp, err := http.Get(fmt.Sprintf("%s/user/%s/recent", services["orders"], userID))
		if err != nil {
			results <- result{key: "orders", err: err}
			return
		}
		defer resp.Body.Close()

		var data interface{}
		json.NewDecoder(resp.Body).Decode(&data)
		results <- result{key: "orders", data: data}
	}()

	// Fetch recommendations
	wg.Add(1)
	go func() {
		defer wg.Done()
		resp, err := http.Get(fmt.Sprintf("%s/recommendations/%s", services["products"], userID))
		if err != nil {
			results <- result{key: "recommendations", err: err}
			return
		}
		defer resp.Body.Close()

		var data interface{}
		json.NewDecoder(resp.Body).Decode(&data)
		results <- result{key: "recommendations", data: data}
	}()

	go func() {
		wg.Wait()
		close(results)
	}()

	// Aggregate results
	dashboard := make(map[string]interface{})
	for res := range results {
		if res.err == nil {
			dashboard[res.key] = res.data
		} else {
			dashboard[res.key] = nil
		}
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(dashboard)
}

// Health Check Handler
func healthHandler(w http.ResponseWriter, r *http.Request) {
	// Check Redis
	redisHealthy := false
	if err := redisClient.Ping(ctx).Err(); err == nil {
		redisHealthy = true
	}

	// Check backend services
	servicesHealth := make(map[string]bool)
	for name, url := range services {
		client := &http.Client{Timeout: 2 * time.Second}
		resp, err := client.Get(url + "/health")
		servicesHealth[name] = err == nil && resp.StatusCode == 200
	}

	allHealthy := redisHealthy
	for _, healthy := range servicesHealth {
		allHealthy = allHealthy && healthy
	}

	status := "healthy"
	if !allHealthy {
		status = "degraded"
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]interface{}{
		"status":    status,
		"timestamp": time.Now().Format(time.RFC3339),
		"redis":     redisHealthy,
		"services":  servicesHealth,
	})
}

func main() {
	// Initialize Redis
	redisClient = redis.NewClient(&redis.Options{
		Addr: "localhost:6379",
		DB:   0,
	})

	// Setup routes
	mux := http.NewServeMux()

	// Public routes
	mux.HandleFunc("/auth/login", loginHandler)
	mux.HandleFunc("/health", healthHandler)

	// Protected routes
	protectedMux := http.NewServeMux()
	protectedMux.HandleFunc("/api/", proxyHandler)
	protectedMux.HandleFunc("/api/dashboard", dashboardHandler)

	// Apply middlewares
	protected := rateLimitMiddleware(authMiddleware(protectedMux))
	mux.Handle("/api/", protected)

	// Root handler
	handler := corsMiddleware(loggingMiddleware(mux))

	// Start server
	log.Println("API Gateway starting on :8080")
	if err := http.ListenAndServe(":8080", handler); err != nil {
		log.Fatal(err)
	}
}
