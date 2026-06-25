"""
Mobile BFF Implementation
Backend for Frontend yang dioptimalkan untuk mobile client
- Smaller payloads
- Aggressive caching
- Bandwidth optimization
- Battery-friendly
"""

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import httpx
import asyncio
from datetime import datetime
import logging
import hashlib
import redis.asyncio as redis

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Mobile BFF", version="1.0.0")

# CORS untuk mobile app
app.add_middleware(
    CORSMiddleware,
    allow_origins=["capacitor://localhost", "ionic://localhost"],  # Mobile app origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration
class Config:
    USER_SERVICE_URL = "http://user-service:8001"
    PRODUCT_SERVICE_URL = "http://product-service:8002"
    ORDER_SERVICE_URL = "http://order-service:8003"
    REDIS_URL = "redis://redis:6379"
    CACHE_TTL = 600  # 10 minutes - aggressive caching untuk mobile
    REQUEST_TIMEOUT = 3.0  # Shorter timeout untuk mobile
    
config = Config()

redis_client: Optional[redis.Redis] = None

@app.on_event("startup")
async def startup():
    global redis_client
    redis_client = await redis.from_url(config.REDIS_URL, encoding="utf-8", decode_responses=True)
    logger.info("Mobile BFF started")

@app.on_event("shutdown")
async def shutdown():
    if redis_client:
        await redis_client.close()

# Models - Simplified untuk mobile
class UserMobile(BaseModel):
    """Simplified user model untuk mobile"""
    id: str
    name: str
    avatar_url: Optional[str] = None  # Thumbnail version
    membership: str  # Simplified field name

class ProductMobile(BaseModel):
    """Simplified product model untuk mobile"""
    id: str
    name: str
    price: float
    currency: str
    image: str  # Single thumbnail image (bukan array)
    rating: Optional[float] = None
    stock_status: str  # "in_stock" | "low_stock" | "out_of_stock"

class OrderMobile(BaseModel):
    """Simplified order model untuk mobile"""
    id: str
    total: float
    status: str
    created_at: str
    item_count: int  # Hanya count, bukan full items

class DashboardMobile(BaseModel):
    """Minimal dashboard untuk mobile"""
    user: UserMobile
    orders: List[OrderMobile]  # Limited to 5 recent
    recommendations: List[ProductMobile]  # Limited to 4

# HTTP Client
class MobileBackendClient:
    def __init__(self):
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(config.REQUEST_TIMEOUT),
            limits=httpx.Limits(max_keepalive_connections=10, max_connections=50)
        )
    
    async def get(self, url: str) -> Dict:
        try:
            response = await self.client.get(url)
            response.raise_for_status()
            return response.json()
        except httpx.TimeoutException:
            logger.error(f"Timeout: {url}")
            raise HTTPException(status_code=504, detail="Service timeout")
        except Exception as e:
            logger.error(f"Error: {url} - {str(e)}")
            raise HTTPException(status_code=500, detail="Service error")
    
    async def close(self):
        await self.client.aclose()

backend_client = MobileBackendClient()

# Cache utilities
async def get_cached(key: str) -> Optional[Dict]:
    if redis_client:
        try:
            data = await redis_client.get(key)
            if data:
                import json
                return json.loads(data)
        except Exception as e:
            logger.warning(f"Cache error: {e}")
    return None

async def set_cached(key: str, value: Dict, ttl: int = config.CACHE_TTL):
    if redis_client:
        try:
            import json
            await redis_client.setex(key, ttl, json.dumps(value))
        except Exception as e:
            logger.warning(f"Cache set error: {e}")

# Transformation utilities
def transform_user_for_mobile(user: Dict) -> UserMobile:
    """Transform user data ke format mobile-optimized"""
    return UserMobile(
        id=user["id"],
        name=user["name"],
        avatar_url=user.get("avatar_url", "").replace("/avatar/", "/avatar/thumb/"),  # Thumbnail version
        membership=user.get("membership_level", "free")
    )

def transform_product_for_mobile(product: Dict) -> ProductMobile:
    """Transform product data ke format mobile-optimized"""
    # Ambil hanya thumbnail image pertama
    images = product.get("images", [])
    thumbnail = images[0].replace("/images/", "/images/thumb/") if images else ""
    
    # Simplify stock status
    stock = product.get("stock", 0)
    if stock > 10:
        stock_status = "in_stock"
    elif stock > 0:
        stock_status = "low_stock"
    else:
        stock_status = "out_of_stock"
    
    return ProductMobile(
        id=product["id"],
        name=product["name"],
        price=product["price"],
        currency=product.get("currency", "USD"),
        image=thumbnail,
        rating=product.get("rating"),
        stock_status=stock_status
    )

def transform_order_for_mobile(order: Dict) -> OrderMobile:
    """Transform order data ke format mobile-optimized"""
    items = order.get("items", [])
    return OrderMobile(
        id=order["id"],
        total=order["total"],
        status=order["status"],
        created_at=order["created_at"],
        item_count=len(items)  # Hanya count untuk list view
    )

# Endpoints

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "mobile-bff"}

@app.get("/api/dashboard", response_model=DashboardMobile)
async def get_dashboard(user_id: str):
    """
    Mobile dashboard - minimal data untuk save bandwidth
    """
    cache_key = f"dashboard:mobile:{user_id}"
    cached = await get_cached(cache_key)
    if cached:
        logger.info(f"Cache hit: dashboard:{user_id}")
        return cached
    
    try:
        # Parallel fetch dengan limit yang lebih kecil
        user_task = backend_client.get(f"{config.USER_SERVICE_URL}/users/{user_id}")
        orders_task = backend_client.get(f"{config.ORDER_SERVICE_URL}/orders?user_id={user_id}&limit=5")  # Only 5 recent
        recommendations_task = backend_client.get(f"{config.PRODUCT_SERVICE_URL}/recommendations/{user_id}?limit=4")  # Only 4
        
        user_data, orders_data, recommendations_data = await asyncio.gather(
            user_task,
            orders_task,
            recommendations_task,
            return_exceptions=True
        )
        
        if isinstance(user_data, Exception):
            raise HTTPException(status_code=500, detail="Failed to fetch user")
        
        # Graceful degradation
        orders = orders_data if not isinstance(orders_data, Exception) else []
        recommendations = recommendations_data if not isinstance(recommendations_data, Exception) else []
        
        # Transform ke mobile format
        response = {
            "user": transform_user_for_mobile(user_data),
            "orders": [transform_order_for_mobile(o) for o in orders],
            "recommendations": [transform_product_for_mobile(p) for p in recommendations]
        }
        
        # Aggressive caching untuk mobile
        await set_cached(cache_key, response, ttl=600)  # 10 minutes
        
        return response
        
    except Exception as e:
        logger.error(f"Dashboard error: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to load dashboard")

@app.get("/api/products/{product_id}")
async def get_product_details(product_id: str):
    """
    Product details untuk mobile - simplified
    """
    cache_key = f"product:mobile:{product_id}"
    cached = await get_cached(cache_key)
    if cached:
        return cached
    
    try:
        product_data = await backend_client.get(f"{config.PRODUCT_SERVICE_URL}/products/{product_id}")
        
        # Transform ke mobile format
        result = {
            "id": product_data["id"],
            "name": product_data["name"],
            "description": product_data.get("description", "")[:200],  # Truncate description
            "price": product_data["price"],
            "currency": product_data.get("currency", "USD"),
            "images": [img.replace("/images/", "/images/thumb/") for img in product_data.get("images", [])[:3]],  # Max 3 thumbnails
            "rating": product_data.get("rating"),
            "stock_status": "in_stock" if product_data.get("stock", 0) > 0 else "out_of_stock"
        }
        
        # Cache result
        await set_cached(cache_key, result, ttl=600)  # 10 minutes
        
        return result
        
    except Exception as e:
        logger.error(f"Product error: {str(e)}")
        raise HTTPException(status_code=404, detail="Product not found")

@app.get("/api/products")
async def search_products(
    q: Optional[str] = None,
    category: Optional[str] = None,
    page: int = 1,
    page_size: int = 12  # Smaller page size untuk mobile
):
    """
    Product search untuk mobile - minimal data
    """
    params = {"page": page, "page_size": page_size}
    if q:
        params["q"] = q
    if category:
        params["category"] = category
    
    # Cache key
    import json
    cache_key = f"products:mobile:{hashlib.md5(json.dumps(params, sort_keys=True).encode()).hexdigest()}"
    
    cached = await get_cached(cache_key)
    if cached:
        return cached
    
    try:
        query_string = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{config.PRODUCT_SERVICE_URL}/products?{query_string}"
        products_data = await backend_client.get(url)
        
        # Transform products ke mobile format
        products = products_data.get("products", [])
        mobile_products = [transform_product_for_mobile(p) for p in products]
        
        result = {
            "products": mobile_products,
            "page": page,
            "has_more": len(products) == page_size
        }
        
        # Cache result
        await set_cached(cache_key, result, ttl=300)  # 5 minutes
        
        return result
        
    except Exception as e:
        logger.error(f"Search error: {str(e)}")
        raise HTTPException(status_code=500, detail="Search failed")

@app.get("/api/orders")
async def get_orders(user_id: str, page: int = 1):
    """
    Order list untuk mobile - minimal info
    """
    page_size = 10  # Fixed small page size
    cache_key = f"orders:mobile:{user_id}:{page}"
    cached = await get_cached(cache_key)
    if cached:
        return cached
    
    try:
        url = f"{config.ORDER_SERVICE_URL}/orders?user_id={user_id}&page={page}&page_size={page_size}"
        orders_data = await backend_client.get(url)
        
        # Transform orders
        orders = orders_data.get("orders", [])
        mobile_orders = [transform_order_for_mobile(o) for o in orders]
        
        result = {
            "orders": mobile_orders,
            "page": page,
            "has_more": len(orders) == page_size
        }
        
        # Cache result
        await set_cached(cache_key, result, ttl=300)  # 5 minutes
        
        return result
        
    except Exception as e:
        logger.error(f"Orders error: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to fetch orders")

@app.get("/api/orders/{order_id}")
async def get_order_details(order_id: str, user_id: str):
    """
    Order detail untuk mobile
    """
    cache_key = f"order:mobile:{order_id}"
    cached = await get_cached(cache_key)
    if cached:
        return cached
    
    try:
        order_data = await backend_client.get(f"{config.ORDER_SERVICE_URL}/orders/{order_id}")
        
        # Verify user owns this order
        if order_data.get("user_id") != user_id:
            raise HTTPException(status_code=403, detail="Forbidden")
        
        # Transform untuk mobile
        result = {
            "id": order_data["id"],
            "total": order_data["total"],
            "status": order_data["status"],
            "created_at": order_data["created_at"],
            "items": [
                {
                    "product_id": item["product_id"],
                    "name": item.get("name", ""),
                    "quantity": item["quantity"],
                    "price": item["price"]
                }
                for item in order_data.get("items", [])
            ]
        }
        
        # Cache result
        await set_cached(cache_key, result, ttl=300)
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Order detail error: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to fetch order")

@app.post("/api/orders")
async def create_order(order_data: Dict[str, Any], user_id: str):
    """
    Create order untuk mobile
    """
    try:
        order_data["user_id"] = user_id
        order_data["created_at"] = datetime.utcnow().isoformat()
        
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
            await redis_client.delete(f"orders:mobile:{user_id}:1")
            await redis_client.delete(f"dashboard:mobile:{user_id}")
        
        # Return minimal response
        return {
            "id": result["id"],
            "status": result["status"],
            "total": result["total"]
        }
        
    except Exception as e:
        logger.error(f"Create order error: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to create order")

@app.get("/api/sync")
async def sync_data(user_id: str, last_sync: Optional[str] = None):
    """
    Sync endpoint untuk mobile offline support
    Return delta changes since last sync
    """
    try:
        # Fetch data yang berubah sejak last_sync
        # Ini simplified version - real implementation butuh change tracking
        
        cache_key = f"sync:mobile:{user_id}"
        
        # Get current dashboard state
        dashboard = await get_dashboard(user_id)
        
        return {
            "sync_timestamp": datetime.utcnow().isoformat(),
            "data": dashboard,
            "next_sync_interval": 600  # Suggest next sync in 10 minutes
        }
        
    except Exception as e:
        logger.error(f"Sync error: {str(e)}")
        raise HTTPException(status_code=500, detail="Sync failed")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
