"""
API Gateway Implementation dengan Python + FastAPI
Lengkap dengan authentication, rate limiting, dan request aggregation
"""

from fastapi import FastAPI, Request, HTTPException, Depends, Header
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import httpx
import jwt
import time
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from functools import wraps
import asyncio
from collections import defaultdict
import redis.asyncio as redis

app = FastAPI(title="API Gateway", version="1.0.0")

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Service Registry
SERVICES = {
    "users": "http://user-service:3001",
    "orders": "http://order-service:3002",
    "products": "http://product-service:3003",
    "payments": "http://payment-service:3004"
}

# JWT Configuration
JWT_SECRET = "your-secret-key-change-in-production"
JWT_ALGORITHM = "HS256"

# Redis untuk rate limiting dan caching
redis_client = redis.from_url("redis://localhost:6379", decode_responses=True)

# Rate Limiting Storage
rate_limit_storage = defaultdict(list)


# ============== Authentication ==============

def create_access_token(data: dict, expires_delta: timedelta = timedelta(hours=1)):
    """Generate JWT token"""
    to_encode = data.copy()
    expire = datetime.utcnow() + expires_delta
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)


async def verify_token(authorization: Optional[str] = Header(None)) -> dict:
    """Verify JWT token dari header"""
    if not authorization:
        raise HTTPException(status_code=401, detail="Token diperlukan")
    
    try:
        scheme, token = authorization.split()
        if scheme.lower() != "bearer":
            raise HTTPException(status_code=401, detail="Invalid authentication scheme")
        
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid authorization header")


# ============== Rate Limiting ==============

class RateLimiter:
    """Simple rate limiter dengan sliding window"""
    
    TIERS = {
        "free": {"requests": 100, "window": 900},      # 100 req / 15 min
        "basic": {"requests": 1000, "window": 900},    # 1000 req / 15 min
        "premium": {"requests": 10000, "window": 900}, # 10k req / 15 min
    }
    
    @classmethod
    async def check_rate_limit(cls, user_id: str, tier: str = "free") -> bool:
        """Check apakah user masih dalam rate limit"""
        key = f"rate_limit:{user_id}"
        current_time = time.time()
        
        limits = cls.TIERS.get(tier, cls.TIERS["free"])
        window = limits["window"]
        max_requests = limits["requests"]
        
        # Get request timestamps dari Redis
        try:
            timestamps = await redis_client.lrange(key, 0, -1)
            timestamps = [float(ts) for ts in timestamps]
        except:
            timestamps = []
        
        # Filter timestamps dalam window
        valid_timestamps = [ts for ts in timestamps if current_time - ts < window]
        
        if len(valid_timestamps) >= max_requests:
            return False
        
        # Add current timestamp
        valid_timestamps.append(current_time)
        
        # Update Redis
        try:
            await redis_client.delete(key)
            if valid_timestamps:
                await redis_client.rpush(key, *valid_timestamps)
                await redis_client.expire(key, window)
        except:
            pass  # Fallback jika Redis down
        
        return True


async def rate_limit_dependency(user: dict = Depends(verify_token)):
    """Dependency untuk check rate limit"""
    user_id = user.get("user_id")
    tier = user.get("tier", "free")
    
    allowed = await RateLimiter.check_rate_limit(user_id, tier)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded",
            headers={"Retry-After": "900"}
        )
    
    return user


# ============== Request Proxying ==============

async def proxy_request(
    service_name: str,
    path: str,
    method: str,
    body: Optional[dict] = None,
    headers: Optional[dict] = None,
    user_id: Optional[str] = None
) -> Dict[str, Any]:
    """Proxy request ke backend service"""
    
    if service_name not in SERVICES:
        raise HTTPException(status_code=404, detail=f"Service {service_name} not found")
    
    service_url = SERVICES[service_name]
    url = f"{service_url}/{path}"
    
    # Add custom headers
    request_headers = headers or {}
    if user_id:
        request_headers["X-User-Id"] = user_id
    request_headers["X-Request-Id"] = f"{int(time.time() * 1000)}"
    
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            if method == "GET":
                response = await client.get(url, headers=request_headers)
            elif method == "POST":
                response = await client.post(url, json=body, headers=request_headers)
            elif method == "PUT":
                response = await client.put(url, json=body, headers=request_headers)
            elif method == "DELETE":
                response = await client.delete(url, headers=request_headers)
            else:
                raise HTTPException(status_code=405, detail="Method not allowed")
            
            return {
                "status_code": response.status_code,
                "data": response.json() if response.text else None
            }
    
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Service timeout")
    except httpx.RequestError as e:
        raise HTTPException(status_code=503, detail=f"Service unavailable: {str(e)}")


# ============== Caching ==============

async def get_cached(key: str) -> Optional[dict]:
    """Get data dari cache"""
    try:
        data = await redis_client.get(key)
        if data:
            import json
            return json.loads(data)
    except:
        pass
    return None


async def set_cache(key: str, data: dict, ttl: int = 300):
    """Set data ke cache dengan TTL"""
    try:
        import json
        await redis_client.setex(key, ttl, json.dumps(data))
    except:
        pass


# ============== API Routes ==============

@app.post("/auth/login")
async def login(credentials: dict):
    """Login endpoint - generate JWT token"""
    # Simplified: Di production, validasi ke auth service
    username = credentials.get("username")
    password = credentials.get("password")
    
    if not username or not password:
        raise HTTPException(status_code=400, detail="Username dan password diperlukan")
    
    # Mock validation (ganti dengan real auth)
    token_data = {
        "user_id": "user123",
        "username": username,
        "tier": "free"
    }
    
    token = create_access_token(token_data)
    
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": 3600
    }


@app.get("/api/{service}/{path:path}")
async def get_proxy(
    service: str,
    path: str,
    request: Request,
    user: dict = Depends(rate_limit_dependency)
):
    """GET request proxy dengan caching"""
    
    # Check cache
    cache_key = f"cache:{service}:{path}:{request.url.query}"
    cached = await get_cached(cache_key)
    if cached:
        return JSONResponse(
            content=cached,
            headers={"X-Cache": "HIT"}
        )
    
    # Forward ke service
    result = await proxy_request(
        service_name=service,
        path=path,
        method="GET",
        user_id=user.get("user_id")
    )
    
    # Cache response jika successful
    if result["status_code"] == 200 and result["data"]:
        await set_cache(cache_key, result["data"], ttl=300)
    
    return JSONResponse(
        content=result["data"],
        status_code=result["status_code"],
        headers={"X-Cache": "MISS"}
    )


@app.post("/api/{service}/{path:path}")
async def post_proxy(
    service: str,
    path: str,
    body: dict,
    user: dict = Depends(rate_limit_dependency)
):
    """POST request proxy"""
    
    result = await proxy_request(
        service_name=service,
        path=path,
        method="POST",
        body=body,
        user_id=user.get("user_id")
    )
    
    return JSONResponse(
        content=result["data"],
        status_code=result["status_code"]
    )


@app.put("/api/{service}/{path:path}")
async def put_proxy(
    service: str,
    path: str,
    body: dict,
    user: dict = Depends(rate_limit_dependency)
):
    """PUT request proxy"""
    
    result = await proxy_request(
        service_name=service,
        path=path,
        method="PUT",
        body=body,
        user_id=user.get("user_id")
    )
    
    return JSONResponse(
        content=result["data"],
        status_code=result["status_code"]
    )


@app.delete("/api/{service}/{path:path}")
async def delete_proxy(
    service: str,
    path: str,
    user: dict = Depends(rate_limit_dependency)
):
    """DELETE request proxy"""
    
    result = await proxy_request(
        service_name=service,
        path=path,
        method="DELETE",
        user_id=user.get("user_id")
    )
    
    return JSONResponse(
        content=result["data"],
        status_code=result["status_code"]
    )


# ============== Request Aggregation ==============

@app.get("/api/dashboard")
async def get_dashboard(user: dict = Depends(rate_limit_dependency)):
    """Aggregate data dari multiple services untuk dashboard"""
    
    user_id = user.get("user_id")
    
    # Parallel requests ke multiple services
    try:
        results = await asyncio.gather(
            proxy_request("users", f"profile/{user_id}", "GET"),
            proxy_request("orders", f"user/{user_id}/recent", "GET"),
            proxy_request("products", f"recommendations/{user_id}", "GET"),
            return_exceptions=True
        )
        
        # Handle individual failures
        user_profile = results[0]["data"] if not isinstance(results[0], Exception) else None
        recent_orders = results[1]["data"] if not isinstance(results[1], Exception) else []
        recommendations = results[2]["data"] if not isinstance(results[2], Exception) else []
        
        return {
            "user": user_profile,
            "orders": recent_orders,
            "recommendations": recommendations
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Dashboard aggregation failed: {str(e)}")


# ============== Health & Metrics ==============

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    
    # Check Redis connection
    redis_healthy = False
    try:
        await redis_client.ping()
        redis_healthy = True
    except:
        pass
    
    # Check backend services
    services_health = {}
    for service_name, service_url in SERVICES.items():
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                response = await client.get(f"{service_url}/health")
                services_health[service_name] = response.status_code == 200
        except:
            services_health[service_name] = False
    
    all_healthy = redis_healthy and all(services_health.values())
    
    return {
        "status": "healthy" if all_healthy else "degraded",
        "timestamp": datetime.utcnow().isoformat(),
        "redis": redis_healthy,
        "services": services_health
    }


@app.get("/metrics")
async def metrics():
    """Metrics endpoint untuk Prometheus"""
    # Simplified metrics
    return {
        "total_requests": "placeholder",
        "active_connections": "placeholder",
        "cache_hit_rate": "placeholder"
    }


# ============== Middleware untuk Logging ==============

@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log semua requests"""
    start_time = time.time()
    
    # Log request
    print(f"[{datetime.utcnow().isoformat()}] {request.method} {request.url.path}")
    
    response = await call_next(request)
    
    # Log response
    duration = time.time() - start_time
    print(f"  └─ {response.status_code} ({duration:.3f}s)")
    
    # Add response headers
    response.headers["X-Response-Time"] = f"{duration:.3f}s"
    
    return response


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
