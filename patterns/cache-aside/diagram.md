# Cache-Aside Pattern - Visual Diagrams

## Basic Flow

```
READ OPERATION:

    Client
      │
      │ 1. Read Request (user_id=123)
      ▼
  ┌─────────┐
  │   App   │
  └────┬────┘
       │
       │ 2. Check cache
       ▼
  ┌─────────────┐
  │    Redis    │
  │    Cache    │
  └─────┬───────┘
        │
        ├─── ✓ HIT ────► 3a. Return data (1-2ms)
        │                    └──► Client
        │
        └─── ✗ MISS
               │
               │ 4. Query database
               ▼
        ┌─────────────┐
        │  PostgreSQL │
        │  Database   │
        └──────┬──────┘
               │
               │ 5. Return data (10-100ms)
               ▼
        ┌─────────────┐
        │    Redis    │
        │ 6. Store in │
        │    cache    │
        └─────────────┘
               │
               │ 7. Return to client
               └──────────────────────► Client


WRITE OPERATION:

    Client
      │
      │ 1. Update Request
      ▼
  ┌─────────┐
  │   App   │
  └────┬────┘
       │
       │ 2. Write to database
       ▼
  ┌─────────────┐
  │  PostgreSQL │
  │  Database   │
  └──────┬──────┘
       │
       │ 3. Success
       ▼
  ┌─────────┐
  │   App   │
  └────┬────┘
       │
       │ 4. Invalidate cache (DELETE key)
       ▼
  ┌─────────────┐
  │    Redis    │
  │ ⊗ Deleted   │
  └─────────────┘
       │
       │ 5. Confirm to client
       └──────────────────────► Client
```

## Thundering Herd Problem

```
WITHOUT PROTECTION:

Popular key expires at t=0

t=0.001s: Request 1 → Cache MISS → Query DB
t=0.002s: Request 2 → Cache MISS → Query DB
t=0.003s: Request 3 → Cache MISS → Query DB
    ...
Result: DATABASE OVERLOAD!


WITH LOCKING:

t=0.001s: Request 1 → Cache MISS → ACQUIRE LOCK → Query DB
t=0.002s: Request 2 → Cache MISS → Wait for lock...
t=0.003s: Request 3 → Cache MISS → Wait for lock...
t=0.500s: Request 1 completes → Store cache → RELEASE LOCK
t=0.501s: Request 2 → Cache HIT (no DB query)
t=0.502s: Request 3 → Cache HIT (no DB query)

Result: Only 1 DB query!
```

## Multi-Level Caching

```
Request
   │
   ├──► L1 Cache (Local, in-memory, ~0.1ms)
   │        ├─ Hit → Return
   │        └─ Miss ↓
   │
   ├──► L2 Cache (Redis, ~1ms)
   │        ├─ Hit → Store in L1 → Return
   │        └─ Miss ↓
   │
   └──► Database (~10-100ms)
            └─ Store in L2 → Store in L1 → Return
```
