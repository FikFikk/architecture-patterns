# CQRS (Command Query Responsibility Segregation)

## Ringkasan

CQRS adalah pattern arsitektur yang memisahkan operasi baca (query) dan tulis (command) ke dalam model yang berbeda. Pattern ini sangat efektif untuk sistem dengan beban baca/tulis yang tidak seimbang dan kebutuhan scalability tinggi.

## Problem yang Diselesaikan

### Masalah Umum dalam Arsitektur Tradisional

1. **Model Data yang Overloaded**
   - Satu model digunakan untuk semua operasi (CRUD)
   - Kompleksitas tinggi karena harus melayani kebutuhan baca dan tulis sekaligus
   - Sulit dioptimasi karena trade-off antara read dan write

2. **Beban yang Tidak Seimbang**
   - Kebanyakan aplikasi memiliki rasio read:write 10:1 hingga 100:1
   - Optimasi untuk satu sisi mengorbankan performa sisi lain
   - Scaling vertikal menjadi mahal dan tidak efisien

3. **Konflik Konkurensi**
   - Lock contention pada database saat baca dan tulis terjadi bersamaan
   - Deadlock dan timeout pada operasi concurrent
   - User experience terdampak karena operasi baca melambat

4. **Kompleksitas Validasi**
   - Validasi write terlalu ketat untuk operasi read
   - Query optimization terbatas karena constraint dari write model
   - Sulit implementasi eventual consistency

### Solusi CQRS

CQRS mengatasi masalah di atas dengan:

- **Pemisahan model**: Command model untuk write, Query model untuk read
- **Optimasi independen**: Masing-masing model dioptimasi sesuai kebutuhannya
- **Scaling horizontal**: Scale read dan write secara terpisah
- **Eventual consistency**: Read model di-update asynchronous dari write model

## Konsep Inti

### Command (Write Side)

**Tanggung jawab:**
- Menerima perintah dari user (Create, Update, Delete)
- Validasi business logic
- Menyimpan data ke write database
- Emit event untuk update read model

**Karakteristik:**
- Menggunakan normalized database schema
- Fokus pada data integrity dan consistency
- Transactional
- Tidak mengembalikan data (kecuali status sukses/gagal)

### Query (Read Side)

**Tanggung jawab:**
- Menerima query dari user
- Mengambil data dari read database
- Mengembalikan data dalam format yang sudah dioptimasi

**Karakteristik:**
- Menggunakan denormalized database schema
- Fokus pada performa dan response time
- Read-only
- Eventually consistent dengan write model

### Event Bus / Message Queue

Komponen yang menghubungkan write dan read side:

- Command side emit event setelah operasi berhasil
- Event handler di read side subscribe dan update query model
- Memungkinkan eventual consistency
- Bisa menggunakan: RabbitMQ, Kafka, Redis Streams, AWS SQS, dll

## Implementation Guide

### Arsitektur Dasar

```
┌──────────────┐
│   Client     │
└──────┬───────┘
       │
       ├─────────────┐
       │             │
       ▼             ▼
┌──────────┐   ┌──────────┐
│ Command  │   │  Query   │
│ Service  │   │ Service  │
└─────┬────┘   └────┬─────┘
      │             │
      │ events      │
      ▼             │
┌──────────┐        │
│ Message  │────────┘
│  Queue   │
└──────────┘
      │
      ▼
┌──────────┐   ┌──────────┐
│  Write   │   │   Read   │
│   DB     │   │    DB    │
└──────────┘   └──────────┘
```

### Langkah Implementasi

#### 1. Identifikasi Bounded Context

Tentukan domain mana yang butuh CQRS. Tidak semua domain butuh pattern ini.

**Kandidat bagus untuk CQRS:**
- Sistem dengan read:write ratio tinggi (>10:1)
- Kebutuhan query yang kompleks dan beragam
- Requirement scalability tinggi
- Domain dengan complex business logic

**Tidak cocok untuk CQRS:**
- CRUD sederhana
- Low traffic
- Tim kecil dengan resource terbatas

#### 2. Desain Command Model

```python
# commands.py - Intent dari user
from dataclasses import dataclass
from typing import Optional
from datetime import datetime

@dataclass
class CreateOrderCommand:
    user_id: str
    items: list
    shipping_address: str
    
@dataclass
class UpdateOrderStatusCommand:
    order_id: str
    status: str
    updated_by: str
```

#### 3. Desain Query Model

```python
# queries.py - Data yang dibutuhkan untuk tampilan
from dataclasses import dataclass
from typing import List, Optional

@dataclass
class OrderListQuery:
    user_id: str
    page: int = 1
    limit: int = 20
    
@dataclass
class OrderDetailQuery:
    order_id: str
    
@dataclass
class OrderSummaryQuery:
    user_id: str
    date_from: Optional[str] = None
    date_to: Optional[str] = None
```

#### 4. Implementasi Command Handler

```python
# command_handlers.py
from typing import Protocol
from .commands import CreateOrderCommand
from .events import OrderCreatedEvent

class EventPublisher(Protocol):
    def publish(self, event): ...

class CreateOrderHandler:
    def __init__(self, db, event_publisher: EventPublisher):
        self.db = db
        self.event_publisher = event_publisher
    
    def handle(self, command: CreateOrderCommand):
        # 1. Validasi
        if not command.items:
            raise ValueError("Order must have items")
        
        # 2. Business logic
        total = sum(item['price'] * item['qty'] for item in command.items)
        
        # 3. Simpan ke write DB (normalized)
        order_id = self.db.orders.insert({
            'user_id': command.user_id,
            'status': 'pending',
            'total': total,
            'created_at': datetime.now()
        })
        
        for item in command.items:
            self.db.order_items.insert({
                'order_id': order_id,
                'product_id': item['product_id'],
                'quantity': item['qty'],
                'price': item['price']
            })
        
        # 4. Publish event
        self.event_publisher.publish(
            OrderCreatedEvent(
                order_id=order_id,
                user_id=command.user_id,
                items=command.items,
                total=total
            )
        )
        
        return {'order_id': order_id, 'status': 'success'}
```

#### 5. Implementasi Query Handler

```python
# query_handlers.py
from .queries import OrderListQuery, OrderDetailQuery

class OrderQueryHandler:
    def __init__(self, read_db):
        self.read_db = read_db
    
    def handle_list(self, query: OrderListQuery):
        # Read dari denormalized DB - semua data sudah joined
        offset = (query.page - 1) * query.limit
        
        orders = self.read_db.execute("""
            SELECT 
                order_id,
                user_id,
                status,
                total,
                item_count,
                created_at,
                updated_at
            FROM order_read_model
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        """, (query.user_id, query.limit, offset))
        
        return [dict(row) for row in orders]
    
    def handle_detail(self, query: OrderDetailQuery):
        # Single query, data sudah di-denormalize
        order = self.read_db.execute("""
            SELECT 
                o.*,
                json_group_array(
                    json_object(
                        'product_name', i.product_name,
                        'quantity', i.quantity,
                        'price', i.price
                    )
                ) as items
            FROM order_read_model o
            LEFT JOIN order_item_read_model i ON o.order_id = i.order_id
            WHERE o.order_id = ?
            GROUP BY o.order_id
        """, (query.order_id,))
        
        return dict(order[0]) if order else None
```

#### 6. Event Handler untuk Sinkronisasi

```python
# event_handlers.py
from .events import OrderCreatedEvent

class OrderReadModelUpdater:
    def __init__(self, read_db):
        self.read_db = read_db
    
    def on_order_created(self, event: OrderCreatedEvent):
        # Update read model (denormalized)
        self.read_db.execute("""
            INSERT INTO order_read_model (
                order_id,
                user_id,
                status,
                total,
                item_count,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
        """, (
            event.order_id,
            event.user_id,
            'pending',
            event.total,
            len(event.items),
            datetime.now()
        ))
        
        for item in event.items:
            self.read_db.execute("""
                INSERT INTO order_item_read_model (
                    order_id,
                    product_id,
                    product_name,
                    quantity,
                    price
                ) VALUES (?, ?, ?, ?, ?)
            """, (
                event.order_id,
                item['product_id'],
                item['name'],  # Denormalized dari product table
                item['qty'],
                item['price']
            ))
```

## Trade-offs dan When to Use/Avoid

### Keuntungan (Pros)

✅ **Scalability Tinggi**
- Read dan write bisa di-scale secara independen
- Horizontal scaling lebih mudah
- Database bisa dioptimasi sesuai workload

✅ **Performance Optimization**
- Read model di-denormalize untuk performa maksimal
- Tidak ada JOIN kompleks di query
- Caching lebih efektif

✅ **Flexibility**
- Multiple read models untuk kebutuhan berbeda
- Bisa pakai database berbeda (write: PostgreSQL, read: Elasticsearch)
- Mudah menambah view baru tanpa ubah write model

✅ **Separation of Concerns**
- Business logic terpisah dari query logic
- Tim bisa bekerja parallel (write team vs read team)
- Testing lebih mudah

### Kekurangan (Cons)

❌ **Kompleksitas Lebih Tinggi**
- Butuh infrastruktur tambahan (message queue)
- Lebih banyak komponen yang harus di-maintain
- Learning curve untuk tim

❌ **Eventual Consistency**
- Read model tidak langsung up-to-date
- Butuh handling untuk stale data
- User experience bisa terdampak jika latency tinggi

❌ **Operational Overhead**
- Monitoring lebih kompleks
- Debugging lebih sulit (distributed system)
- Data synchronization issues

❌ **Cost**
- Lebih banyak infrastructure
- Butuh message queue yang reliable
- Mungkin butuh database terpisah

### Kapan Menggunakan CQRS

**✅ Gunakan jika:**

1. **Read:Write ratio tinggi** (>10:1)
   - E-commerce (banyak browsing, sedikit checkout)
   - Social media feed (banyak scroll, sedikit post)
   - Analytics dashboard (banyak view, sedikit input)

2. **Kebutuhan query yang beragam**
   - Multiple dashboards dengan view berbeda
   - Reporting yang kompleks
   - Search dengan berbagai filter

3. **Scalability requirement tinggi**
   - Traffic tidak predictable
   - Butuh scale up/down otomatis
   - Performance adalah priority

4. **Complex business logic**
   - Domain-driven design
   - Event sourcing
   - Audit trail yang lengkap

**❌ Hindari jika:**

1. **CRUD sederhana**
   - Blog sederhana
   - Contact form
   - Basic user management

2. **Team kecil dengan resource terbatas**
   - Startup fase awal
   - Internal tools
   - POC / prototype

3. **Low traffic**
   - Admin panel internal
   - Tools untuk ops team
   - Sistem yang jarang diakses

4. **Strong consistency requirement**
   - Financial transactions (tanpa Event Sourcing)
   - Inventory management real-time
   - Booking systems yang tidak boleh double booking

## Scalability Considerations

### 1. Database Scaling

**Write Side:**
```
- Gunakan RDBMS (PostgreSQL, MySQL) untuk ACID compliance
- Vertical scaling untuk consistency
- Master-slave replication jika perlu
- Sharding berdasarkan tenant/region
```

**Read Side:**
```
- Bisa pakai NoSQL (MongoDB, Cassandra) untuk denormalized data
- Horizontal scaling lebih mudah
- Read replicas banyak
- Caching agresif (Redis, Memcached)
```

### 2. Message Queue Scaling

**Pilihan teknologi:**

- **RabbitMQ**: Good for moderate scale, easy setup
- **Apache Kafka**: Best for high throughput, event streaming
- **Redis Streams**: Simple, good performance untuk small-medium scale
- **AWS SQS/SNS**: Managed service, auto-scaling
- **Google Pub/Sub**: Global scale, low latency

**Pattern:**
```python
# Topic-based untuk multiple consumers
{
    "topic": "orders",
    "event": "OrderCreated",
    "consumers": [
        "order-read-model-updater",
        "notification-service",
        "analytics-service"
    ]
}
```

### 3. Read Model Variations

Buat multiple read models untuk use case berbeda:

```python
# Read Model 1: Order List (untuk dashboard)
order_list_read_model = {
    'order_id': 'uuid',
    'user_name': 'string',  # denormalized
    'status': 'string',
    'total': 'decimal',
    'item_count': 'int',
    'created_at': 'timestamp'
}

# Read Model 2: Order Analytics (untuk reporting)
order_analytics_read_model = {
    'date': 'date',
    'total_orders': 'int',
    'total_revenue': 'decimal',
    'avg_order_value': 'decimal',
    'top_products': 'json'
}

# Read Model 3: Search Index (untuk Elasticsearch)
order_search_model = {
    'order_id': 'keyword',
    'user_name': 'text',
    'product_names': 'text',  # full-text search
    'status': 'keyword',
    'tags': 'keyword[]'
}
```

### 4. Caching Strategy

```python
# L1: In-memory cache (application level)
# L2: Distributed cache (Redis)
# L3: Read database

class CachedQueryHandler:
    def __init__(self, query_handler, cache):
        self.query_handler = query_handler
        self.cache = cache
    
    def handle(self, query):
        cache_key = f"query:{query.__class__.__name__}:{hash(query)}"
        
        # Try L1 cache
        if result := self.cache.get(cache_key):
            return result
        
        # Query DB
        result = self.query_handler.handle(query)
        
        # Store in cache
        self.cache.set(cache_key, result, ttl=300)  # 5 minutes
        
        return result
```

### 5. Eventual Consistency Handling

```python
# Client-side: Optimistic UI update
async function createOrder(order) {
    // 1. Show loading state
    showLoading();
    
    // 2. Send command
    const result = await api.post('/commands/create-order', order);
    
    // 3. Optimistic update
    updateUIOptimistically(result.order_id);
    
    // 4. Poll atau WebSocket untuk konfirmasi
    pollOrderStatus(result.order_id);
}

# Server-side: Version checking
class QueryHandler:
    def handle_with_version(self, query, expected_version):
        result = self.handle(query)
        
        if result.version < expected_version:
            # Read model belum up-to-date
            return {
                'status': 'pending',
                'retry_after': 1000  # ms
            }
        
        return result
```

## Real-world Examples

### 1. **Netflix**

**Use case**: Content recommendation dan user activity

**Implementation:**
- Write: User interactions (play, pause, rate) → Cassandra
- Read: Personalized recommendations → Pre-computed results in Elasticsearch
- Event: User action → Kafka → ML pipeline → Update recommendations

**Scale:**
- Millions of users concurrent
- Billions of events per day
- Sub-second recommendation updates

### 2. **Amazon**

**Use case**: Product catalog dan inventory

**Implementation:**
- Write: Inventory updates, pricing changes → Aurora (PostgreSQL)
- Read: Product search, browse → Elasticsearch dengan multiple indexes
- Event: Inventory change → SNS/SQS → Update search index + cache invalidation

**Benefits:**
- Search bisa di-scale independent dari inventory updates
- Multiple view untuk different use cases (search, browse, recommendations)
- Cache aggressively untuk high traffic

### 3. **Tokopedia / Bukalapak**

**Use case**: Order management

**Implementation:**
- Write: Create order, payment → MySQL (transactional)
- Read: Order history, tracking → MongoDB (denormalized)
- Event: Order state change → RabbitMQ → Update multiple read models

**Benefit untuk pasar Indonesia:**
- Handle traffic spike saat flash sale
- Different read models untuk seller vs buyer view
- Analytics untuk dashboard seller

### 4. **Grab / Gojek**

**Use case**: Ride/order matching dan tracking

**Implementation:**
- Write: Driver location, order placement → Redis + PostgreSQL
- Read: Nearby drivers, order status → Redis Geospatial + Elasticsearch
- Event: Location update → Redis Streams → Real-time map update

**Characteristics:**
- Ultra-low latency requirement (<100ms)
- Real-time updates via WebSocket
- Geospatial queries untuk matching

### 5. **Stripe**

**Use case**: Payment processing

**Implementation:**
- Write: Payment transactions → PostgreSQL (ACID)
- Read: Transaction history, analytics → BigQuery (data warehouse)
- Event: Payment event → Kafka → Multiple downstream services

**Why it works:**
- Strong consistency untuk transactions
- Eventual consistency acceptable untuk analytics
- Audit trail lengkap via event log

## Advanced Patterns

### 1. Event Sourcing + CQRS

Kombinasi powerful untuk audit trail:

```python
# Event store as source of truth
events = [
    OrderCreatedEvent(...),
    ItemAddedEvent(...),
    OrderPaidEvent(...),
    OrderShippedEvent(...)
]

# Rebuild state dari events
def rebuild_order_state(order_id):
    events = event_store.get_events(order_id)
    state = OrderState()
    for event in events:
        state = state.apply(event)
    return state

# Rebuild read model
def rebuild_read_model():
    for event in event_store.get_all_events():
        read_model_updater.handle(event)
```

### 2. Saga Pattern untuk Distributed Transactions

```python
# Orchestration-based saga
class OrderSaga:
    def __init__(self, command_bus, event_bus):
        self.command_bus = command_bus
        self.event_bus = event_bus
    
    async def execute(self, order):
        try:
            # Step 1: Reserve inventory
            await self.command_bus.send(ReserveInventoryCommand(order.items))
            
            # Step 2: Process payment
            await self.command_bus.send(ProcessPaymentCommand(order.total))
            
            # Step 3: Create shipment
            await self.command_bus.send(CreateShipmentCommand(order.id))
            
            # Success: emit event
            self.event_bus.publish(OrderCompletedEvent(order.id))
            
        except Exception as e:
            # Rollback: compensating transactions
            await self.compensate(order)
```

### 3. Polyglot Persistence

```python
# Different databases untuk different needs
write_db = PostgreSQL()      # ACID compliance
read_db_main = MongoDB()     # Flexible schema, fast reads
read_db_search = Elasticsearch()  # Full-text search
read_db_analytics = BigQuery()    # Data warehouse
cache = Redis()              # In-memory cache

# Event handler update semua read models
class MultiReadModelUpdater:
    def on_order_created(self, event):
        # Update main read model
        read_db_main.insert(event.to_document())
        
        # Update search index
        read_db_search.index(event.to_search_doc())
        
        # Stream to analytics (async, batch)
        read_db_analytics.stream(event.to_analytics_row())
        
        # Invalidate cache
        cache.delete(f"order:{event.order_id}")
```

## Monitoring dan Troubleshooting

### Key Metrics

```python
metrics = {
    # Command side
    'command.execution_time': histogram,
    'command.success_rate': counter,
    'command.failure_count': counter,
    
    # Query side
    'query.execution_time': histogram,
    'query.cache_hit_rate': gauge,
    'query.result_size': histogram,
    
    # Synchronization
    'event.processing_lag': gauge,  # Penting!
    'event.queue_depth': gauge,
    'event.processing_time': histogram,
    
    # Consistency
    'read_model.sync_delay': gauge,  # Eventual consistency delay
    'read_model.rebuild_time': histogram
}
```

### Common Issues

**1. Read Model Lagging**

```python
# Symptom: User tidak lihat data terbaru
# Solution: Monitor dan alert

def check_sync_lag():
    last_write_event = get_last_event_timestamp('write')
    last_read_update = get_last_event_timestamp('read')
    lag = last_write_event - last_read_update
    
    if lag > threshold:
        alert("Read model lagging by {} seconds".format(lag))
```

**2. Event Processing Failure**

```python
# Implement retry dengan exponential backoff
class ResilientEventHandler:
    def handle(self, event, retry=0):
        try:
            self.process(event)
        except Exception as e:
            if retry < max_retries:
                delay = 2 ** retry  # exponential backoff
                schedule_retry(event, delay, retry + 1)
            else:
                # Dead letter queue
                dlq.send(event, error=str(e))
                alert("Event processing failed permanently")
```

**3. Data Inconsistency**

```python
# Periodic reconciliation
def reconcile():
    write_ids = set(write_db.get_all_ids())
    read_ids = set(read_db.get_all_ids())
    
    missing = write_ids - read_ids
    extra = read_ids - write_ids
    
    if missing:
        rebuild_read_model(missing)
    
    if extra:
        alert("Orphaned read model records: {}".format(extra))
```

## Testing Strategy

### 1. Unit Tests

```python
def test_create_order_command():
    # Arrange
    command = CreateOrderCommand(user_id='123', items=[...])
    handler = CreateOrderHandler(mock_db, mock_publisher)
    
    # Act
    result = handler.handle(command)
    
    # Assert
    assert result['status'] == 'success'
    mock_publisher.publish.assert_called_once()
```

### 2. Integration Tests

```python
def test_end_to_end_order_creation():
    # 1. Send command
    command_bus.send(CreateOrderCommand(...))
    
    # 2. Wait untuk event processing
    wait_for_event_processing()
    
    # 3. Verify read model updated
    order = query_handler.handle(OrderDetailQuery(order_id))
    assert order is not None
    assert order['status'] == 'pending'
```

### 3. Chaos Engineering

```python
# Test eventual consistency
def test_read_model_catches_up_after_failure():
    # 1. Create order
    create_order()
    
    # 2. Simulate read model failure
    kill_read_model_service()
    
    # 3. Restart service
    start_read_model_service()
    
    # 4. Verify catch-up
    wait_until(lambda: read_model_is_synced())
```

## Migration Strategy

Jika ingin migrate dari monolith ke CQRS:

### Phase 1: Add Reads (Low Risk)

```python
# Keep existing writes, add new read models
class OrderService:
    def create_order(self, order):
        # Existing code
        result = self.legacy_create(order)
        
        # New: Publish event untuk read model
        self.event_bus.publish(OrderCreatedEvent(...))
        
        return result
```

### Phase 2: Migrate Writes (Medium Risk)

```python
# Separate command handlers
class OrderService:
    def create_order(self, order):
        # New command-based approach
        command = CreateOrderCommand(...)
        return self.command_handler.handle(command)
```

### Phase 3: Optimize (High Impact)

```python
# Separate databases, optimize read models
write_db = PostgreSQL()
read_db = MongoDB()  # Denormalized
```

## Kesimpulan

CQRS adalah pattern powerful untuk sistem dengan requirement scalability tinggi dan beban read/write yang tidak seimbang. Pattern ini memberikan flexibility untuk optimize read dan write secara independen, tetapi dengan trade-off berupa kompleksitas yang lebih tinggi.

**Key Takeaways:**

1. ✅ Gunakan CQRS jika benar-benar butuh (high read:write ratio, complex queries)
2. ⚠️ Mulai sederhana, jangan over-engineering di awal
3. 🔄 Eventual consistency adalah trade-off yang harus diterima
4. 📊 Monitoring sangat penting untuk detect dan fix sync issues
5. 🧪 Testing harus cover happy path dan failure scenarios

## Referensi dan Further Reading

### Papers & Articles

1. **Greg Young - CQRS Documents**
   - https://cqrs.files.wordpress.com/2010/11/cqrs_documents.pdf
   - Paper original yang menjelaskan CQRS pattern

2. **Martin Fowler - CQRS**
   - https://martinfowler.com/bliki/CQRS.html
   - Overview dan kapan menggunakan CQRS

3. **Microsoft - CQRS Pattern**
   - https://docs.microsoft.com/en-us/azure/architecture/patterns/cqrs
   - Implementation guide dengan Azure

### Books

1. **"Domain-Driven Design" - Eric Evans**
   - Foundational concepts untuk bounded context

2. **"Implementing Domain-Driven Design" - Vaughn Vernon**
   - Practical implementation termasuk CQRS

3. **"Microservices Patterns" - Chris Richardson**
   - CQRS dalam konteks microservices

### Videos

1. **Greg Young - CQRS and Event Sourcing**
   - https://www.youtube.com/watch?v=JHGkaShoyNs
   - Deep dive dari creator pattern

2. **Udi Dahan - If you're not doing CQRS, you're doing it wrong**
   - Penjelasan kenapa CQRS penting untuk distributed systems

### Open Source Examples

1. **Axon Framework (Java)**
   - https://github.com/AxonFramework/AxonFramework
   - Full-featured CQRS + Event Sourcing framework

2. **EventStore**
   - https://www.eventstore.com/
   - Database yang didesain untuk CQRS + Event Sourcing

3. **NServiceBus**
   - https://particular.net/nservicebus
   - Messaging platform yang support CQRS pattern

### Indonesian Tech Blogs

1. **Gojek Engineering Blog**
   - https://www.gojek.io/blog
   - Real-world examples dari unicorn Indonesia

2. **Tokopedia Engineering**
   - https://medium.com/tokopedia-engineering
   - Scale challenges dan solutions

---

**Dibuat oleh**: Hermes Agent - Autonomous Architecture Research  
**Tanggal**: 20 Juni 2026  
**Pattern Category**: Architectural Pattern  
**Complexity**: Advanced  
**Best For**: High-scale, read-heavy applications
