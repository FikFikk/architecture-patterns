# Event Sourcing Pattern - Architecture Diagrams

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                          CLIENT / UI                            │
└────────────────┬───────────────────────────────┬────────────────┘
                 │                               │
          WRITE (Commands)                READ (Queries)
                 │                               │
                 ▼                               ▼
┌────────────────────────────────┐   ┌──────────────────────────┐
│       COMMAND HANDLER          │   │    QUERY HANDLER         │
│  (Validate & Process Commands) │   │  (Query Read Models)     │
└────────────┬───────────────────┘   └──────────┬───────────────┘
             │                                   │
             ▼                                   ▼
┌────────────────────────────────┐   ┌──────────────────────────┐
│         AGGREGATE              │   │    READ MODELS           │
│  (Business Logic & State)      │   │  (Projections)           │
│  - Order                       │   │  - Order List View       │
│  - BankAccount                 │   │  - Account Statement     │
│  - User                        │   │  - Analytics Dashboard   │
└────────────┬───────────────────┘   └──────────▲───────────────┘
             │                                   │
             │ Emit Events                       │ Subscribe
             ▼                                   │
┌────────────────────────────────────────────────┴────────────────┐
│                        EVENT STORE                              │
│  (Append-Only Log - Source of Truth)                           │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │  Aggregate: order_123                                   │  │
│  │  ┌──────────────────────────────────────────────────┐  │  │
│  │  │ v1: OrderPlaced        @ 2026-06-20T10:00:00Z   │  │  │
│  │  │ v2: PaymentReceived    @ 2026-06-20T10:05:00Z   │  │  │
│  │  │ v3: OrderShipped       @ 2026-06-20T11:00:00Z   │  │  │
│  │  │ v4: OrderDelivered     @ 2026-06-20T15:00:00Z   │  │  │
│  │  └──────────────────────────────────────────────────┘  │  │
│  └─────────────────────────────────────────────────────────┘  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
                             │
                             │ Event Stream
                             ▼
                  ┌──────────────────────┐
                  │    EVENT BUS         │
                  │  (Pub/Sub)           │
                  └──────────┬───────────┘
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
       ┌─────────┐    ┌─────────┐    ┌─────────┐
       │Projection│    │Projection│    │External │
       │Handler 1│    │Handler 2│    │Services │
       └─────────┘    └─────────┘    └─────────┘
```

## Write Side Flow (Command Processing)

```
User Action
    │
    ▼
┌───────────────┐
│   Command     │  PlaceOrder(items, address, customerId)
└───────┬───────┘
        │
        ▼
┌───────────────────────┐
│  Command Handler      │
│  - Validate input     │
│  - Load aggregate     │
│  - Execute command    │
└───────┬───────────────┘
        │
        ▼
┌───────────────────────┐
│   Aggregate           │
│  - Check invariants   │────❌──→ Business Rule Violation
│  - Generate event     │
└───────┬───────────────┘
        │
        ▼
┌───────────────────────┐
│   Event Store         │
│  - Append event       │
│  - Check version      │────❌──→ Concurrency Error
│  - Return new event   │
└───────┬───────────────┘
        │
        ▼
┌───────────────────────┐
│  Event Bus            │
│  - Publish event      │
└───────┬───────────────┘
        │
        ▼
    ✅ Success
```

## Read Side Flow (Query Processing)

```
User Query
    │
    ▼
┌───────────────┐
│  Query        │  GetOrderById(orderId)
└───────┬───────┘
        │
        ▼
┌───────────────────────┐
│  Query Handler        │
│  - Route to correct   │
│    read model         │
└───────┬───────────────┘
        │
        ▼
┌───────────────────────┐
│  Read Model           │
│  (Projection)         │
│  - PostgreSQL         │
│  - Redis              │
│  - Elasticsearch      │
└───────┬───────────────┘
        │
        ▼
    Return Data


[How Projection is Built]

Event Store ──→ Event Bus
                   │
                   ▼
           Projection Handler
                   │
                   ▼
            Update Read Model
```

## State Transitions (Order Example)

```
                    ┌──────────────┐
                    │   Initial    │
                    └──────┬───────┘
                           │
                    OrderPlaced Event
                           │
                           ▼
                    ┌──────────────┐
                    │   PENDING    │
                    └──────┬───────┘
                           │
                  PaymentReceived Event
                           │
                           ▼
                    ┌──────────────┐
            ┌───────┤     PAID     ├───────┐
            │       └──────┬───────┘       │
            │              │               │
     OrderCancelled    OrderShipped   OrderCancelled
         Event            Event            Event
            │              │               │
            ▼              ▼               ▼
     ┌──────────┐   ┌──────────┐   ┌──────────┐
     │CANCELLED │   │ SHIPPED  │   │CANCELLED │
     └──────────┘   └────┬─────┘   └──────────┘
                         │
                  OrderDelivered Event
                         │
                         ▼
                  ┌──────────────┐
                  │  DELIVERED   │
                  └──────────────┘
```

## Event Replay Visualization

```
Current State = Replay(All Events)

┌─────────────────────────────────────────────────────────────┐
│  Event Store: order_123                                     │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  v1: OrderPlaced                                           │
│      { items: [...], total: 100000 }                       │
│                                                             │
│  v2: PaymentReceived                                       │
│      { method: "credit_card", amount: 100000 }             │
│                                                             │
│  v3: OrderShipped                                          │
│      { trackingNumber: "TRACK123" }                        │
│                                                             │
└─────────────────────────────────────────────────────────────┘
                         │
                         │ Replay All Events
                         ▼
              ┌──────────────────┐
              │  Initial State   │
              │  {}              │
              └────────┬─────────┘
                       │
              Apply v1 (OrderPlaced)
                       │
                       ▼
              ┌──────────────────┐
              │  State after v1  │
              │  status: PENDING │
              │  total: 100000   │
              └────────┬─────────┘
                       │
              Apply v2 (PaymentReceived)
                       │
                       ▼
              ┌──────────────────┐
              │  State after v2  │
              │  status: PAID    │
              │  payment: {...}  │
              └────────┬─────────┘
                       │
              Apply v3 (OrderShipped)
                       │
                       ▼
              ┌──────────────────┐
              │  Current State   │
              │  status: SHIPPED │
              │  tracking: {...} │
              └──────────────────┘
```

## Temporal Query (Time Travel)

```
Question: "What was the order status at 10:30 AM?"

┌─────────────────────────────────────────────────────────────┐
│  Event Timeline                                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  10:00 AM ──→ OrderPlaced                                  │
│                                                             │
│  10:05 AM ──→ PaymentReceived                              │
│                                                             │
│              ⏰ Query Time: 10:30 AM                        │
│                                                             │
│  11:00 AM ──→ OrderShipped                                 │
│                                                             │
│  15:00 AM ──→ OrderDelivered                               │
│                                                             │
└─────────────────────────────────────────────────────────────┘

Answer: Replay events until 10:30 AM
        → OrderPlaced (10:00)
        → PaymentReceived (10:05)
        → Status = PAID ✓
```

## Snapshot Optimization

```
Without Snapshot:
┌─────────────────────────────────────────────────────────┐
│  Load Aggregate                                         │
│  → Replay 10,000 events 😰                              │
│  → Slow! (~5 seconds)                                   │
└─────────────────────────────────────────────────────────┘

With Snapshot:
┌─────────────────────────────────────────────────────────┐
│  Load Aggregate                                         │
│  → Load snapshot at version 9,000 (instant)            │
│  → Replay 1,000 recent events                          │
│  → Fast! (~100ms) 🚀                                    │
└─────────────────────────────────────────────────────────┘

Snapshot Strategy:
┌──────────────────────────────────────────────────────┐
│  Event Store                                         │
│  ┌────────────────────────────────┐                 │
│  │ v1-v1000   [many events...]    │                 │
│  └────────────────────────────────┘                 │
│               ↓                                      │
│         Snapshot Store                              │
│  ┌────────────────────────────────┐                 │
│  │ Snapshot @ v1000               │                 │
│  │ { state: {...}, version: 1000 }│                 │
│  └────────────────────────────────┘                 │
│               +                                      │
│  ┌────────────────────────────────┐                 │
│  │ v1001-v1500 [recent events]    │                 │
│  └────────────────────────────────┘                 │
│               ↓                                      │
│       Current State (v1500)                         │
└──────────────────────────────────────────────────────┘
```

## Multiple Projections

```
                    ┌──────────────────┐
                    │   Event Store    │
                    └────────┬─────────┘
                             │
                             │ Event Stream
                             ▼
                    ┌──────────────────┐
                    │    Event Bus     │
                    └─────────┬────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
        ▼                     ▼                     ▼
┌───────────────┐   ┌───────────────┐   ┌───────────────┐
│ Projection 1  │   │ Projection 2  │   │ Projection 3  │
│ Order List    │   │ Order Detail  │   │  Analytics    │
├───────────────┤   ├───────────────┤   ├───────────────┤
│ [Optimized    │   │ [Normalized   │   │ [Time-series  │
│  for listing] │   │  with joins]  │   │  aggregated]  │
│               │   │               │   │               │
│ Redis Cache   │   │ PostgreSQL    │   │ ClickHouse    │
└───────────────┘   └───────────────┘   └───────────────┘
        │                     │                     │
        ▼                     ▼                     ▼
   List View UI        Detail View UI      Analytics Dashboard
```

## Concurrency Control

```
Scenario: Two users update same aggregate simultaneously

User A                          User B
  │                              │
  ├─ Load Order (v3)            ├─ Load Order (v3)
  │                              │
  ├─ Modify Order               ├─ Modify Order
  │                              │
  ├─ Append Event (expect v3)   │
  │  ✅ Success → v4             │
  │                              │
  │                              ├─ Append Event (expect v3)
  │                              │  ❌ ConcurrencyError!
  │                              │     (Current version is v4)
  │                              │
  │                              ├─ Reload Order (v4)
  │                              ├─ Reapply changes
  │                              ├─ Append Event (expect v4)
  │                              │  ✅ Success → v5

Optimistic Concurrency Control:
- Each event knows expected version
- Event Store checks version before append
- Concurrent modifications detected
- Application retries with latest version
```

## Event Schema Evolution

```
Version 1:
{
  "eventType": "OrderPlaced",
  "data": {
    "orderId": "123",
    "items": [...],
    "address": "Jl. Sudirman"  // String
  }
}

Version 2 (Enhanced):
{
  "eventType": "OrderPlaced",
  "version": 2,
  "data": {
    "orderId": "123",
    "items": [...],
    "shippingAddress": {      // Now structured
      "street": "Jl. Sudirman",
      "city": "Jakarta",
      "postalCode": "12190"
    }
  }
}

Upcasting (Transform v1 → v2 on read):
┌────────────────────────────────────────┐
│  Event Store (Immutable)               │
│  - v1 events stay as v1                │
│  - v2 events stay as v2                │
└──────────────┬─────────────────────────┘
               │
               ▼
        Upcaster Layer
               │
    ┌──────────┴──────────┐
    │                     │
    ▼                     ▼
  v1 Event            v2 Event
    │                     │
    └──────────┬──────────┘
               │
               ▼
     All events as v2 format
```

## Deployment Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      Load Balancer                          │
└────────┬──────────────────────────────────────┬─────────────┘
         │                                      │
         │ Write Requests                       │ Read Requests
         ▼                                      ▼
┌────────────────────┐              ┌────────────────────────┐
│  Command Service   │              │   Query Service        │
│  (Stateless)       │              │   (Stateless)          │
│  - Horizontal      │              │   - Horizontal         │
│    Scaling         │              │     Scaling            │
└────────┬───────────┘              └────────┬───────────────┘
         │                                   │
         ▼                                   ▼
┌────────────────────┐              ┌────────────────────────┐
│   Event Store      │──Event Bus──→│   Read Models          │
│   - EventStoreDB   │              │   - PostgreSQL         │
│   - Kafka          │              │   - Redis              │
│   - Replicated     │              │   - Elasticsearch      │
└────────────────────┘              │   - Replicas           │
                                    └────────────────────────┘
```

---

**Visualization Tools:**
- Mermaid: https://mermaid.live/
- PlantUML: https://plantuml.com/
- Draw.io: https://draw.io/

**Interactive Demos:**
- Run `python example_order.py` untuk melihat event flow
- Run `python example_bank.py` untuk temporal queries
- Run `pytest test_event_sourcing.py -v` untuk test scenarios
