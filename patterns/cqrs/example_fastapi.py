"""
CQRS Pattern - FastAPI Implementation
Production-ready example dengan PostgreSQL, Redis, dan RabbitMQ
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import asyncio
import json
from enum import Enum


# ============================================================================
# MODELS & SCHEMAS
# ============================================================================

class OrderStatus(str, Enum):
    PENDING = "pending"
    PAID = "paid"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


class CreateOrderRequest(BaseModel):
    user_id: str
    items: List[dict]
    shipping_address: str


class UpdateOrderStatusRequest(BaseModel):
    status: OrderStatus


class OrderResponse(BaseModel):
    order_id: str
    status: str


class OrderDetailResponse(BaseModel):
    order_id: str
    user_id: str
    status: str
    total: float
    item_count: int
    items: List[dict]
    created_at: str
    updated_at: Optional[str] = None


class OrderListResponse(BaseModel):
    orders: List[OrderDetailResponse]
    total: int
    page: int
    limit: int


# ============================================================================
# MOCK DATABASE LAYER (Replace with real DB in production)
# ============================================================================

class MockWriteDB:
    """Mock write database (PostgreSQL in production)"""
    
    def __init__(self):
        self.orders = {}
        self.order_items = {}
        self.products = {
            'P001': {'id': 'P001', 'name': 'Laptop', 'price': 10000000, 'stock': 10},
            'P002': {'id': 'P002', 'name': 'Mouse', 'price': 150000, 'stock': 50},
            'P003': {'id': 'P003', 'name': 'Keyboard', 'price': 500000, 'stock': 30},
        }
        self._counter = 1
    
    async def create_order(self, user_id: str, items: List[dict], address: str):
        """Create order with transaction"""
        order_id = f"ORD{self._counter:05d}"
        self._counter += 1
        
        # Validate and calculate
        total = 0
        for item in items:
            product = self.products.get(item['product_id'])
            if not product:
                raise ValueError(f"Product not found: {item['product_id']}")
            if product['stock'] < item['quantity']:
                raise ValueError(f"Insufficient stock for {product['name']}")
            total += product['price'] * item['quantity']
        
        # Insert order
        self.orders[order_id] = {
            'order_id': order_id,
            'user_id': user_id,
            'status': 'pending',
            'total': total,
            'shipping_address': address,
            'created_at': datetime.now()
        }
        
        # Insert order items
        self.order_items[order_id] = items
        
        # Update stock
        for item in items:
            self.products[item['product_id']]['stock'] -= item['quantity']
        
        return order_id, total, items
    
    async def update_order_status(self, order_id: str, new_status: str):
        """Update order status"""
        if order_id not in self.orders:
            raise ValueError(f"Order not found: {order_id}")
        
        old_status = self.orders[order_id]['status']
        self.orders[order_id]['status'] = new_status
        self.orders[order_id]['updated_at'] = datetime.now()
        
        return old_status
    
    async def get_order(self, order_id: str):
        """Get order from write DB"""
        return self.orders.get(order_id)


class MockReadDB:
    """Mock read database (MongoDB/Elasticsearch in production)"""
    
    def __init__(self):
        self.orders = {}
    
    async def upsert_order(self, order_data: dict):
        """Insert or update order in read model"""
        self.orders[order_data['order_id']] = order_data
    
    async def get_order(self, order_id: str):
        """Get order detail"""
        return self.orders.get(order_id)
    
    async def get_orders_by_user(self, user_id: str, page: int = 1, limit: int = 20):
        """Get orders with pagination"""
        user_orders = [
            order for order in self.orders.values()
            if order['user_id'] == user_id
        ]
        
        # Sort by created_at desc
        user_orders.sort(key=lambda x: x['created_at'], reverse=True)
        
        # Pagination
        start = (page - 1) * limit
        end = start + limit
        
        return {
            'orders': user_orders[start:end],
            'total': len(user_orders),
            'page': page,
            'limit': limit
        }
    
    async def get_order_summary(self, user_id: str):
        """Get user order summary"""
        user_orders = [
            order for order in self.orders.values()
            if order['user_id'] == user_id
        ]
        
        return {
            'total_orders': len(user_orders),
            'total_spent': sum(order['total'] for order in user_orders),
            'orders_by_status': {
                status: len([o for o in user_orders if o['status'] == status])
                for status in ['pending', 'paid', 'shipped', 'delivered', 'cancelled']
            }
        }


class MockEventBus:
    """Mock event bus (RabbitMQ/Kafka in production)"""
    
    def __init__(self):
        self.handlers = {}
    
    def subscribe(self, event_type: str, handler):
        """Subscribe to event"""
        if event_type not in self.handlers:
            self.handlers[event_type] = []
        self.handlers[event_type].append(handler)
    
    async def publish(self, event_type: str, event_data: dict):
        """Publish event asynchronously"""
        print(f"📢 Event published: {event_type}")
        
        if event_type in self.handlers:
            # Simulate async processing
            for handler in self.handlers[event_type]:
                asyncio.create_task(handler(event_data))


class MockCache:
    """Mock cache (Redis in production)"""
    
    def __init__(self):
        self.data = {}
    
    async def get(self, key: str):
        """Get from cache"""
        return self.data.get(key)
    
    async def set(self, key: str, value: dict, ttl: int = 300):
        """Set to cache with TTL"""
        self.data[key] = value
        # In production, implement TTL
    
    async def delete(self, key: str):
        """Delete from cache"""
        if key in self.data:
            del self.data[key]


# ============================================================================
# APPLICATION LAYER
# ============================================================================

class CommandService:
    """Service untuk handle commands (write operations)"""
    
    def __init__(self, write_db: MockWriteDB, event_bus: MockEventBus, cache: MockCache):
        self.write_db = write_db
        self.event_bus = event_bus
        self.cache = cache
    
    async def create_order(self, user_id: str, items: List[dict], address: str):
        """Create order command"""
        # Execute command
        order_id, total, items = await self.write_db.create_order(user_id, items, address)
        
        # Get enriched item data
        enriched_items = []
        for item in items:
            product = self.write_db.products[item['product_id']]
            enriched_items.append({
                'product_id': item['product_id'],
                'product_name': product['name'],
                'quantity': item['quantity'],
                'price': product['price']
            })
        
        # Publish event
        await self.event_bus.publish('OrderCreated', {
            'order_id': order_id,
            'user_id': user_id,
            'items': enriched_items,
            'total': total,
            'timestamp': datetime.now().isoformat()
        })
        
        # Invalidate cache
        await self.cache.delete(f"user_orders:{user_id}")
        await self.cache.delete(f"user_summary:{user_id}")
        
        return order_id
    
    async def update_order_status(self, order_id: str, new_status: str):
        """Update order status command"""
        # Execute command
        old_status = await self.write_db.update_order_status(order_id, new_status)
        
        # Get order data
        order = await self.write_db.get_order(order_id)
        
        # Publish event
        await self.event_bus.publish('OrderStatusChanged', {
            'order_id': order_id,
            'old_status': old_status,
            'new_status': new_status,
            'timestamp': datetime.now().isoformat()
        })
        
        # Invalidate cache
        await self.cache.delete(f"order:{order_id}")
        await self.cache.delete(f"user_orders:{order['user_id']}")
        await self.cache.delete(f"user_summary:{order['user_id']}")
        
        return True


class QueryService:
    """Service untuk handle queries (read operations)"""
    
    def __init__(self, read_db: MockReadDB, cache: MockCache):
        self.read_db = read_db
        self.cache = cache
    
    async def get_order_detail(self, order_id: str):
        """Get order detail with caching"""
        # Try cache first (L1)
        cache_key = f"order:{order_id}"
        cached = await self.cache.get(cache_key)
        if cached:
            print(f"💾 Cache hit: {cache_key}")
            return cached
        
        # Query from read DB
        print(f"🔍 Cache miss, querying DB: {cache_key}")
        order = await self.read_db.get_order(order_id)
        
        if order:
            # Store in cache
            await self.cache.set(cache_key, order, ttl=300)
        
        return order
    
    async def get_user_orders(self, user_id: str, page: int = 1, limit: int = 20):
        """Get user orders with caching"""
        cache_key = f"user_orders:{user_id}:{page}:{limit}"
        cached = await self.cache.get(cache_key)
        if cached:
            print(f"💾 Cache hit: {cache_key}")
            return cached
        
        print(f"🔍 Cache miss, querying DB: {cache_key}")
        result = await self.read_db.get_orders_by_user(user_id, page, limit)
        
        await self.cache.set(cache_key, result, ttl=60)
        return result
    
    async def get_user_summary(self, user_id: str):
        """Get user summary with caching"""
        cache_key = f"user_summary:{user_id}"
        cached = await self.cache.get(cache_key)
        if cached:
            print(f"💾 Cache hit: {cache_key}")
            return cached
        
        print(f"🔍 Cache miss, querying DB: {cache_key}")
        summary = await self.read_db.get_order_summary(user_id)
        
        await self.cache.set(cache_key, summary, ttl=300)
        return summary


class ReadModelUpdater:
    """Event handler untuk update read model"""
    
    def __init__(self, read_db: MockReadDB):
        self.read_db = read_db
    
    async def on_order_created(self, event: dict):
        """Handle OrderCreated event"""
        print(f"📝 Updating read model: OrderCreated({event['order_id']})")
        
        order_data = {
            'order_id': event['order_id'],
            'user_id': event['user_id'],
            'status': 'pending',
            'total': event['total'],
            'item_count': len(event['items']),
            'items': event['items'],
            'created_at': event['timestamp'],
            'updated_at': event['timestamp']
        }
        
        await self.read_db.upsert_order(order_data)
        print(f"✅ Read model updated")
    
    async def on_order_status_changed(self, event: dict):
        """Handle OrderStatusChanged event"""
        print(f"📝 Updating read model: OrderStatusChanged({event['order_id']})")
        
        order = await self.read_db.get_order(event['order_id'])
        if order:
            order['status'] = event['new_status']
            order['updated_at'] = event['timestamp']
            await self.read_db.upsert_order(order)
            print(f"✅ Read model updated")


# ============================================================================
# FASTAPI APPLICATION
# ============================================================================

# Initialize dependencies
write_db = MockWriteDB()
read_db = MockReadDB()
event_bus = MockEventBus()
cache = MockCache()

command_service = CommandService(write_db, event_bus, cache)
query_service = QueryService(read_db, cache)
read_model_updater = ReadModelUpdater(read_db)

# Subscribe event handlers
event_bus.subscribe('OrderCreated', read_model_updater.on_order_created)
event_bus.subscribe('OrderStatusChanged', read_model_updater.on_order_status_changed)

# Create FastAPI app
app = FastAPI(
    title="CQRS Order Service",
    description="Production-ready CQRS implementation with FastAPI",
    version="1.0.0"
)


# ============================================================================
# COMMAND ENDPOINTS (Write Operations)
# ============================================================================

@app.post("/commands/orders", response_model=OrderResponse, status_code=201)
async def create_order(request: CreateOrderRequest, background_tasks: BackgroundTasks):
    """
    Create a new order (Command)
    
    - Validates items and stock
    - Creates order in write database
    - Publishes OrderCreated event
    - Read model akan di-update async via event handler
    """
    try:
        order_id = await command_service.create_order(
            request.user_id,
            request.items,
            request.shipping_address
        )
        
        return OrderResponse(
            order_id=order_id,
            status="success"
        )
    
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


@app.patch("/commands/orders/{order_id}/status", response_model=OrderResponse)
async def update_order_status(order_id: str, request: UpdateOrderStatusRequest):
    """
    Update order status (Command)
    
    - Updates status in write database
    - Publishes OrderStatusChanged event
    - Read model akan di-update async via event handler
    """
    try:
        await command_service.update_order_status(order_id, request.status)
        
        return OrderResponse(
            order_id=order_id,
            status="success"
        )
    
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


# ============================================================================
# QUERY ENDPOINTS (Read Operations)
# ============================================================================

@app.get("/queries/orders/{order_id}", response_model=OrderDetailResponse)
async def get_order_detail(order_id: str):
    """
    Get order detail (Query)
    
    - Reads from read database (denormalized)
    - Uses cache for performance
    - No joins needed, data already denormalized
    """
    order = await query_service.get_order_detail(order_id)
    
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    return OrderDetailResponse(**order)


@app.get("/queries/users/{user_id}/orders", response_model=OrderListResponse)
async def get_user_orders(user_id: str, page: int = 1, limit: int = 20):
    """
    Get user orders with pagination (Query)
    
    - Reads from read database
    - Cached for performance
    - Supports pagination
    """
    result = await query_service.get_user_orders(user_id, page, limit)
    
    orders = [OrderDetailResponse(**order) for order in result['orders']]
    
    return OrderListResponse(
        orders=orders,
        total=result['total'],
        page=result['page'],
        limit=result['limit']
    )


@app.get("/queries/users/{user_id}/summary")
async def get_user_summary(user_id: str):
    """
    Get user order summary (Query)
    
    - Pre-computed data dari read model
    - Heavy caching
    - Optimized untuk dashboard
    """
    summary = await query_service.get_user_summary(user_id)
    return summary


# ============================================================================
# HEALTH & MONITORING ENDPOINTS
# ============================================================================

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "components": {
            "write_db": "ok",
            "read_db": "ok",
            "event_bus": "ok",
            "cache": "ok"
        }
    }


@app.get("/metrics")
async def metrics():
    """Metrics endpoint untuk monitoring"""
    return {
        "write_db": {
            "total_orders": len(write_db.orders),
            "total_products": len(write_db.products)
        },
        "read_db": {
            "total_orders": len(read_db.orders)
        },
        "cache": {
            "total_keys": len(cache.data)
        }
    }


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    
    print("🚀 Starting CQRS Order Service with FastAPI")
    print("📖 API Docs: http://localhost:8000/docs")
    print("📊 Metrics: http://localhost:8000/metrics")
    print()
    
    uvicorn.run(app, host="0.0.0.0", port=8000)
