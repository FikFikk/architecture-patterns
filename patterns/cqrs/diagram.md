# CQRS Architecture Diagrams

## 1. High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         CLIENT / USER                            │
└──────────────┬────────────────────────────┬─────────────────────┘
               │                            │
               │ Commands                   │ Queries
               │ (Write)                    │ (Read)
               ▼                            ▼
┌──────────────────────────┐    ┌──────────────────────────┐
│    COMMAND SERVICE       │    │     QUERY SERVICE        │
│  (Business Logic)        │    │   (Data Retrieval)       │
└──────────┬───────────────┘    └────────┬─────────────────┘
           │                              │
           │ Validate &                   │ Read from
           │ Execute                      │ Read Model
           ▼                              ▼
┌──────────────────────────┐    ┌──────────────────────────┐
│   WRITE DATABASE         │    │    READ DATABASE         │
│   (Normalized)           │    │    (Denormalized)        │
│   - PostgreSQL           │    │    - MongoDB             │
│   - MySQL                │    │    - Elasticsearch       │
└──────────┬───────────────┘    └──────────────────────────┘
           │
           │ Emit Events
           ▼
┌─────────────────────────────────────────────────────────────────┐
│                       EVENT BUS / MESSAGE QUEUE                  │
│                     (RabbitMQ / Kafka / Redis)                   │
└──────────┬──────────────────────────────────────────────────────┘
           │
           │ Subscribe & Process
           ▼
┌─────────────────────────────────────────────────────────────────┐
│                      EVENT HANDLERS                              │
│              (Update Read Model, Notifications, etc)             │
└─────────────────────────────────────────────────────────────────┘
```

## 2. Command Flow (Write Path)

```
User Request
    │
    │ POST /commands/orders
    ▼
┌────────────────────────┐
│  API Gateway/Router    │
└───────────┬────────────┘
            │
            ▼
┌────────────────────────┐
│  Command Handler       │
│  1. Validate           │
│  2. Business Logic     │
│  3. Execute            │
└───────────┬────────────┘
            │
            │ Transaction
            ▼
┌────────────────────────┐
│  Write Database        │
│  (ACID Compliant)      │
│  - orders              │
│  - order_items         │
└───────────┬────────────┘
            │
            │ Success
            ▼
┌────────────────────────┐
│  Publish Event         │
│  OrderCreatedEvent     │
└───────────┬────────────┘
            │
            ▼
┌────────────────────────┐
│  Message Queue         │
└────────────────────────┘
            │
            ▼ (async)
┌────────────────────────┐
│  Event Consumers       │
│  - Update Read Model   │
│  - Send Notifications  │
│  - Update Analytics    │
└────────────────────────┘
```

## 3. Query Flow (Read Path)

```
User Request
    │
    │ GET /queries/orders/123
    ▼
┌────────────────────────┐
│  API Gateway/Router    │
└───────────┬────────────┘
            │
            ▼
┌────────────────────────┐
│  Query Handler         │
└───────────┬────────────┘
            │
            │ Check Cache (L1)
            ▼
┌────────────────────────┐
│  Cache Layer (Redis)   │
└───────────┬────────────┘
            │
            │ Cache Miss
            ▼
┌────────────────────────┐
│  Read Database         │
│  (Denormalized)        │
│  Single Query, No Join │
└───────────┬────────────┘
            │
            │ Store in Cache
            ▼
┌────────────────────────┐
│  Return to Client      │
└────────────────────────┘
```

## 4. Event-Driven Synchronization

```
Write Side                          Read Side
──────────                         ──────────

┌──────────┐                      ┌──────────┐
│  Orders  │                      │  Orders  │
│  Table   │                      │(Document)│
└────┬─────┘                      └──────────┘
     │                                  ▲
     │ INSERT                           │
     │ order_id: 1                      │ UPDATE
     │ user_id: 123                     │ (async)
     │ status: pending                  │
     │ total: 1000000                   │
     ▼                                  │
┌──────────┐                           │
│Order Items│                          │
│  Table   │                           │
└────┬─────┘                           │
     │                                  │
     │ INSERT                           │
     │ order_id: 1                      │
     │ product_id: P001                 │
     │ quantity: 2                      │
     │                                  │
     │ Emit Event                       │
     ▼                                  │
┌─────────────────────┐                │
│  OrderCreatedEvent  │                │
│  {                  │────────────────┘
│    order_id: 1,     │  Event Handler
│    user_id: 123,    │  denormalizes data
│    items: [         │  and updates read DB
│      {product_id,   │
│       product_name, │
│       quantity}     │
│    ],               │
│    total: 1000000   │
│  }                  │
└─────────────────────┘
```

## 5. Read Model Denormalization

**Write Model (Normalized):**
```
┌─────────────────┐         ┌─────────────────┐
│     orders      │         │   order_items   │
├─────────────────┤         ├─────────────────┤
│ order_id (PK)   │────┐    │ id (PK)         │
│ user_id         │    └───<│ order_id (FK)   │
│ status          │         │ product_id (FK) │
│ total           │         │ quantity        │
│ created_at      │         │ price           │
└─────────────────┘         └─────────────────┘
                                     │
                                     │
                                     ▼
                            ┌─────────────────┐
                            │    products     │
                            ├─────────────────┤
                            │ product_id (PK) │
                            │ name            │
                            │ price           │
                            │ stock           │
                            └─────────────────┘
```

**Read Model (Denormalized):**
```
┌─────────────────────────────────────────────┐
│          order_read_model                   │
├─────────────────────────────────────────────┤
│ order_id                                    │
│ user_id                                     │
│ status                                      │
│ total                                       │
│ item_count                                  │
│ items: [                     ← Embedded!    │
│   {                                         │
│     product_id: "P001",                     │
│     product_name: "Laptop",  ← Denormalized │
│     quantity: 2,                            │
│     price: 10000000                         │
│   }                                         │
│ ]                                           │
│ created_at                                  │
│ updated_at                                  │
└─────────────────────────────────────────────┘

Keuntungan:
✓ Single query, no JOIN
✓ Fast reads
✓ Easy to cache
✓ Optimized untuk UI
```

## 6. Scaling Strategy

```
                    ┌──────────────┐
                    │ Load Balancer│
                    └──────┬───────┘
                           │
            ┌──────────────┼──────────────┐
            │                             │
            ▼                             ▼
┌────────────────────┐        ┌────────────────────┐
│  Command Service   │        │   Query Service    │
│   Instance 1       │        │   Instance 1       │
└──────────┬─────────┘        └──────────┬─────────┘
           │                             │
┌──────────┴─────────┐        ┌──────────┴─────────┐
│  Command Service   │        │   Query Service    │
│   Instance 2       │        │   Instance 2       │
└──────────┬─────────┘        └──────────┬─────────┘
           │                             │
           │ Scale Independently         │
           │                             │
           ▼                             ▼
┌────────────────────┐        ┌────────────────────┐
│  Write DB          │        │  Read DB Cluster   │
│  (Master)          │        │  (Multiple Slaves) │
│                    │        │  ┌──────┐          │
│  ┌──────┐          │        │  │Slave1│          │
│  │Master│          │        │  ├──────┤          │
│  └───┬──┘          │        │  │Slave2│          │
│      │             │        │  ├──────┤          │
│      │ Replicate   │        │  │Slave3│          │
│      ▼             │        │  └──────┘          │
│  ┌──────┐          │        │                    │
│  │Slave │          │        │  + Cache Layer     │
│  └──────┘          │        │  (Redis Cluster)   │
└────────────────────┘        └────────────────────┘
           │                             ▲
           │                             │
           └──────────┬──────────────────┘
                      │
                      ▼
           ┌────────────────────┐
           │  Message Queue     │
           │  (Kafka Cluster)   │
           │  ┌──────┐          │
           │  │Topic1│          │
           │  ├──────┤          │
           │  │Topic2│          │
           │  ├──────┤          │
           │  │Topic3│          │
           │  └──────┘          │
           └────────────────────┘

Horizontal Scaling:
- Command Service: 2-5 instances (CPU bound)
- Query Service: 5-20 instances (traffic dependent)
- Write DB: 1 master + N slaves
- Read DB: N replicas (scale by traffic)
- Message Queue: Partitioned topics
```

## 7. Data Flow Timeline

```
Time │ Write Side          │ Event Bus        │ Read Side
─────┼─────────────────────┼──────────────────┼────────────────
t0   │ Command received    │                  │
     │ Validate            │                  │
     │                     │                  │
t1   │ Begin transaction   │                  │
     │ INSERT orders       │                  │
     │ INSERT order_items  │                  │
     │ Commit              │                  │
     │                     │                  │
t2   │ Publish event ──────┼─→ Event received│
     │ Return success      │                  │
     │                     │                  │
t3   │                     │ Dispatch to      │
     │                     │ subscribers      │
     │                     │                  │
t4   │                     │                  │ Event handler
     │                     │                  │ UPDATE read_model
     │                     │                  │ Invalidate cache
     │                     │                  │
t5   │                     │                  │ Read model synced

                    ▲
                    │
            Eventual Consistency Gap
            (typically < 100ms)
```

## 8. Polyglot Persistence

```
┌────────────────────────────────────────────────────────────┐
│                    Application Layer                        │
└───┬────────────┬───────────────┬──────────────┬────────────┘
    │            │               │              │
    │ Commands   │ Events        │ Queries      │ Cache
    ▼            ▼               ▼              ▼
┌─────────┐ ┌─────────┐ ┌──────────────┐ ┌──────────┐
│PostgreSQL│ │ Kafka   │ │  MongoDB     │ │  Redis   │
│         │ │         │ │              │ │          │
│ ACID    │ │ Stream  │ │ Flexible     │ │ In-mem   │
│ Strong  │ │ Event   │ │ Denormalized │ │ Fast     │
│ Consist.│ │ Log     │ │ Scalable     │ │ TTL      │
└─────────┘ └─────────┘ └──────────────┘ └──────────┘
     │                         │
     │                         │
     └──────────┬──────────────┘
                │
                ▼
        ┌──────────────┐
        │ Elasticsearch│
        │              │
        │ Full-text    │
        │ Search       │
        │ Analytics    │
        └──────────────┘
```

## 9. Monitoring Dashboard

```
┌─────────────────────────────────────────────────────────────┐
│                   CQRS System Metrics                        │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Command Performance          Query Performance             │
│  ┌────────────────┐          ┌────────────────┐            │
│  │ Avg: 45ms      │          │ Avg: 12ms      │            │
│  │ P95: 120ms     │          │ P95: 35ms      │            │
│  │ P99: 250ms     │          │ P99: 80ms      │            │
│  └────────────────┘          └────────────────┘            │
│                                                              │
│  Event Processing             Sync Lag                      │
│  ┌────────────────┐          ┌────────────────┐            │
│  │ Rate: 1.2k/s   │          │ Avg: 45ms      │ ⚠️         │
│  │ Success: 99.8% │          │ Max: 250ms     │            │
│  │ DLQ: 2         │          │ P99: 180ms     │            │
│  └────────────────┘          └────────────────┘            │
│                                                              │
│  Cache Hit Rate               Database Load                 │
│  ┌────────────────┐          ┌────────────────┐            │
│  │ Queries: 85%   │ ✓        │ Write: 20%     │            │
│  │ Commands: N/A  │          │ Read: 45%      │            │
│  │ Memory: 65%    │          │ Connections: 50│            │
│  └────────────────┘          └────────────────┘            │
└─────────────────────────────────────────────────────────────┘

Key Alerts:
🔴 Sync lag > 500ms: CRITICAL
🟡 Sync lag > 200ms: WARNING
🟢 Sync lag < 100ms: HEALTHY
```

## 10. Failure Scenarios & Recovery

```
Scenario 1: Event Handler Failure
─────────────────────────────────
Command Side        Event Bus         Read Side
     │                  │                 │
     │ Success          │                 │
     ├─────────────────>│                 │
     │                  ├────────────────>│ ✗ FAIL
     │                  │                 │
     │                  │ Retry (exp backoff)
     │                  ├────────────────>│ ✗ FAIL
     │                  │                 │
     │                  │ Retry           │
     │                  ├────────────────>│ ✗ FAIL
     │                  │                 │
     │                  ├──> Dead Letter Queue
     │                  │
     │                  │ Manual Recovery:
     │                  │ - Alert ops
     │                  │ - Replay from event log
     │                  │ - Rebuild read model

Scenario 2: Network Partition
─────────────────────────────
Write DB Available      Read DB Unavailable
      │                       │
      │ Commands work         │ Queries fail
      │ Events queued         │ Return cached data
      │                       │ Or return 503
      │                       │
      └───────────────────────┘
              │
         Network restored
              │
      ┌───────▼────────┐
      │ Event replay   │
      │ Read sync up   │
      │ System healthy │
      └────────────────┘
```

---

**Notes:**
- Semua diagram menggunakan ASCII art untuk kompatibilitas
- Dapat di-render dengan tools seperti Mermaid atau PlantUML untuk visualisasi yang lebih baik
- Diagram ini fokus pada alur dan konsep, bukan implementasi spesifik
