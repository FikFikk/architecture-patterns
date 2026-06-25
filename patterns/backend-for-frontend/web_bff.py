"""
Web BFF Implementation
Backend for Frontend yang dioptimalkan untuk web client
"""

from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import httpx
import asyncio
from datetime import datetime
import logging
from functools import lru_cache
import redis.asyncio as redis

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Web BFF", version="1.0.0")

# CORS configuration untuk web client
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://web.example.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration
class Config:
    USER_SERVICE_URL = "http://user-service:8001"
    PRODUCT_SERVICE_URL = "http://product-service:8002"
    ORDER_SERVICE_URL = "http://order-service:8003"
    REVIEW_SERVICE_URL = "http://review-service:8004"
    REDIS_URL = "redis://redis:6379"
    CACHE_TTL = 300  # 5 minutes
    REQUEST_TIMEOUT = 5.0

config = Config()

# Redis client
redis_client: Optional[redis.Redis] = None

@app.on_event("startup")
async def startup():
    global redis_client
    redis_client = await redis.from_url(config.REDIS_URL, encoding="utf-8", decode_responses=True)
    logger.info("Web BFF started")

@app.on_event("shutdown")
async def shutdown():
    if redis_client:
        await redis_client.close()
    logger.info("Web BFF shutdown")

# Models
class User(BaseModel):
    id: str
    name: str
    email: str
    avatar_url: Optional[str] = None
    membership_level: str
    joined_date: str

class Product(BaseModel):
    id: str
    name: str
    description: str
    price: float
    currency: str
    images: List[str]
    category: str
    stock: int
    rating: Optional[float] = None
    review_count: Optional[int] = 0

class Order(BaseModel):
    id: str
    user_id: str
    items: List[Dict[str, Any]]
    total: float
    status: str
    created_at: str
    estimated_delivery: Optional[str] = None

class DashboardResponse(BaseModel):
    user: User
    recent_orders: List[Order]
    recommended_products: List[Product]
    stats: Dict[str, Any]

# HTTP Client dengan connection pooling
class BackendClient:
    def __init__(self):
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(config.REQUEST_TIMEOUT),
            limits=httpx.Limits(max_keepalive_connections=20, max_connections=100)
        )
    
    async def get(self, url: str, headers: Optional[Dict] = None) -> Dict:
        """GET request dengan error handling"""
        try:
            response = await self.client.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
        except httpx.TimeoutException:
            logger.error(f"Timeout calling {url}")
            raise HTTPException(status_code=504, detail="Backend service timeout")
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error calling {url}: {e.response.status_code}")
            raise HTTPException(status_code=e.response.status_code, detail="Backend service error")
        except Exception as e:
            logger.error(f"Error calling {url}: {str(e)}")
            raise HTTPException(status_code=500, detail="Internal server error")
    
    async def close(self):
        await self.client.aclose()

backend_client = BackendClient()

# Cache utilities
async def get_cached(key: str) -> Optional[Dict]:
    """Get dari Redis cache"""
    if redis_client:
        try:
            data = await redis_client.get(key)
            if data:
                import json
                return json.loads(data)
        except Exception as e:
            logger.warning(f"Cache get error: {e}")
    return None

async def set_cached(key: str, value: Dict, ttl: int = config.CACHE_TTL):
    """Set ke Redis cache dengan TTL"""
    if redis_client:
        try:
            import json
            await redis_client.setex(key, ttl, json.dumps(value))
        except Exception as e:
            logger.warning(f"Cache set error: {e}")

# Endpoints

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "web-bff", "timestamp": datetime.utcnow().isoformat()}

@app.get("/api/dashboard", response_model=DashboardResponse)
async def get_dashboard(user_id: str, request: Request):
    """
    Dashboard endpoint untuk web client
    Aggregate data dari multiple backend services
    """
    # Check cache
    cache_key = f"dashboard:web:{user_id}"
    cached = await get_cached(cache_key)
    if cached:
        logger.info(f"Cache hit for dashboard: {user_id}")
        return cached
    
    # Parallel fetch dari multiple services
    try:
        user_task = backend_client.get(f"{config.USER_SERVICE_URL}/users/{user_id}")
        orders_task = backend_client.get(f"{config.ORDER_SERVICE_URL}/orders?user_id={user_id}&limit=10")
        recommendations_task = backend_client.get(f"{config.PRODUCT_SERVICE_URL}/recommendations/{user_id}?limit=8")
        
        user_data, orders_data, recommendations_data = await asyncio.gather(
            user_task,
            orders_task,
            recommendations_task,
            return_exceptions=True
        )
        
        # Handle partial failures
        if isinstance(user_data, Exception):
            raise HTTPException(status_code=500, detail="Failed to fetch user data")
        
        # Graceful degradation untuk non-critical data
        orders = orders_data if not isinstance(orders_data, Exception) else []
        recommendations = recommendations_data if not isinstance(recommendations_data, Exception) else []
        
        # Aggregate response
        response = {
            "user": user_data,
            "recent_orders": orders,
            "recommended_products": recommendations,
            "stats": {
                "total_orders": len(orders),
                "lifetime_value": sum(order.get("total", 0) for order in orders),
                "member_since": user_data.get("joined_date"),
            }
        }
        
        # Cache result
        await set_cached(cache_key, response, ttl=60)  # 1 minute cache
        
        return response
        
    except Exception as e:
        logger.error(f"Dashboard error: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to load dashboard")

@app.get("/api/products/{product_id}", response_model=Product)
async def get_product_details(product_id: str):
    """
    Product details endpoint untuk web client
    Includes full product info + reviews + recommendations
    """
    cache_key = f"product:web:{product_id}"
    cached = await get_cached(cache_key)
    if cached:
        return cached
    
    try:
        # Parallel fetch product details dan reviews
        product_task = backend_client.get(f"{config.PRODUCT_SERVICE_URL}/products/{product_id}")
        reviews_task = backend_client.get(f"{config.REVIEW_SERVICE_URL}/reviews?product_id={product_id}&limit=50")
        
        product_data, reviews_data = await asyncio.gather(
            product_task,
            reviews_task,
            return_exceptions=True
        )
        
        if isinstance(product_data, Exception):
            raise HTTPException(status_code=404, detail="Product not found")
        
        # Aggregate reviews jika available
        if not isinstance(reviews_data, Exception) and reviews_data:
            reviews = reviews_data.get("reviews", [])
            product_data["rating"] = sum(r["rating"] for r in reviews) / len(reviews) if reviews else None
            product_data["review_count"] = len(reviews)
            product_data["reviews"] = reviews  # Web client dapat handle full reviews
        
        # Cache result
        await set_cached(cache_key, product_data, ttl=300)  # 5 minutes
        
        return product_data
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Product details error: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to fetch product details")

@app.get("/api/products")
async def search_products(
    q: Optional[str] = None,
    category: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    page: int = 1,
    page_size: int = 24  # Web dapat handle larger page size
):
    """
    Product search endpoint untuk web client
    Support advanced filters dan larger page size
    """
    # Build query params
    params = {
        "page": page,
        "page_size": page_size
    }
    if q:
        params["q"] = q
    if category:
        params["category"] = category
    if min_price:
        params["min_price"] = min_price
    if max_price:
        params["max_price"] = max_price
    
    # Cache key dari query params
    import hashlib
    import json
    cache_key = f"products:web:{hashlib.md5(json.dumps(params, sort_keys=True).encode()).hexdigest()}"
    
    cached = await get_cached(cache_key)
    if cached:
        return cached
    
    try:
        query_string = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{config.PRODUCT_SERVICE_URL}/products?{query_string}"
        products_data = await backend_client.get(url)
        
        # Cache result
        await set_cached(cache_key, products_data, ttl=180)  # 3 minutes
        
        return products_data
        
    except Exception as e:
        logger.error(f"Product search error: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to search products")

@app.get("/api/orders")
async def get_orders(user_id: str, page: int = 1, page_size: int = 20):
    """
    Order history endpoint untuk web client
    Returns detailed order information
    """
    cache_key = f"orders:web:{user_id}:{page}"
    cached = await get_cached(cache_key)
    if cached:
        return cached
    
    try:
        url = f"{config.ORDER_SERVICE_URL}/orders?user_id={user_id}&page={page}&page_size={page_size}"
        orders_data = await backend_client.get(url)
        
        # Enrich orders dengan product details (web client butuh detail)
        orders = orders_data.get("orders", [])
        for order in orders:
            product_ids = [item["product_id"] for item in order.get("items", [])]
            if product_ids:
                # Fetch product details untuk setiap item
                product_tasks = [
                    backend_client.get(f"{config.PRODUCT_SERVICE_URL}/products/{pid}")
                    for pid in product_ids
                ]
                products = await asyncio.gather(*product_tasks, return_exceptions=True)
                
                # Map product details ke order items
                product_map = {p["id"]: p for p in products if not isinstance(p, Exception)}
                for item in order.get("items", []):
                    if item["product_id"] in product_map:
                        item["product_details"] = product_map[item["product_id"]]
        
        result = {
            "orders": orders,
            "page": page,
            "page_size": page_size,
            "total": orders_data.get("total", len(orders))
        }
        
        # Cache result
        await set_cached(cache_key, result, ttl=60)  # 1 minute
        
        return result
        
    except Exception as e:
        logger.error(f"Orders error: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to fetch orders")

@app.post("/api/orders")
async def create_order(order_data: Dict[str, Any], user_id: str):
    """
    Create order endpoint
    Validate dan forward ke order service
    """
    try:
        # Add user_id ke order data
        order_data["user_id"] = user_id
        order_data["created_at"] = datetime.utcnow().isoformat()
        
        # Forward ke order service
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{config.ORDER_SERVICE_URL}/orders",
                json=order_data,
                timeout=10.0
            )
            response.raise_for_status()
            result = response.json()
        
        # Invalidate cache
        if redis_client:
            await redis_client.delete(f"orders:web:{user_id}:1")
            await redis_client.delete(f"dashboard:web:{user_id}")
        
        return result
        
    except Exception as e:
        logger.error(f"Create order error: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to create order")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
