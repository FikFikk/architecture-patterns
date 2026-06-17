# Saga Pattern Anti-Patterns

## 1. Non-Idempotent Operations

### The Problem
Executing saga steps multiple times produces different results, leading to data corruption.

### Example (Bad)
```python
def reserve_inventory(product_id, quantity):
    current = db.get_inventory(product_id)
    new_quantity = current - quantity
    db.update_inventory(product_id, new_quantity)
    # If this runs twice, inventory double-decrements!
```

### Why It's Bad
- Network failures cause retries
- Duplicate messages in message brokers
- Compensation may run multiple times
- Results in incorrect inventory counts, duplicate charges, etc.

### Correct Approach
```python
def reserve_inventory(idempotency_key, product_id, quantity):
    # Check if already processed
    if idempotency_store.exists(idempotency_key):
        return idempotency_store.get(idempotency_key)
    
    # Use database constraints for atomic operation
    result = db.execute_update(
        product_id=product_id,
        quantity_delta=-quantity,
        min_quantity=quantity
    )
    
    if not result.success:
        raise InsufficientInventoryError()
    
    # Store result
    idempotency_store.put(idempotency_key, result)
    return result
```

### Key Principles
- Use idempotency keys (saga_id + step_id)
- Use database constraints (optimistic locking, unique constraints)
- Store operation results for replay
- Design for "at-least-once" delivery

---

## 2. Non-Compensatable Operations

### The Problem
Designing saga steps that cannot be reversed.

### Examples (Bad)
- Sending an email (can't unsend)
- Triggering external webhook (can't undo)
- Printing shipping label (irreversible)

### Why It's Bad
If saga fails after these steps, cannot fully compensate leading to customer confusion and operational issues.

### Correct Approaches

**Option 1: Move to End of Saga**
Execute irreversible actions only after all reversible steps succeed.

**Option 2: Use Semantic Compensation**
Send follow-up communication explaining the cancellation.

**Option 3: Use Two-Phase Approach**
Reserve/prepare first (compensatable), then commit only after saga succeeds.

---

## 3. Missing Timeout Handling

### The Problem
Saga steps hang indefinitely, blocking resources and preventing compensation.

### Why It's Bad
- External services may be slow or unresponsive
- Database locks held indefinitely
- Saga instances accumulate in "IN_PROGRESS" state
- System degrades over time

### Correct Approach
Configure timeouts for every saga step with proper fallback handling and trigger compensation on timeout.

---

## 4. Lack of Observability

### The Problem
Running sagas in production without proper monitoring, making debugging impossible.

### What's Missing
- No logging of saga progress
- No distributed tracing
- No metrics on success/failure rates
- No visibility into which step failed

### Why It's Bad
Cannot diagnose production issues, identify patterns in failures, or optimize performance.

### Correct Approach
Implement structured logging, distributed tracing, metrics collection, and real-time dashboards.

---

## 5. Distributed Transactions in Disguise

### The Problem
Using saga pattern but requiring ACID properties, defeating the purpose.

### Example
Money transfers between accounts require strong consistency. Saga introduces inconsistency window where money could be lost.

### Correct Approach
Use local ACID transaction if both accounts in same database, or use ledger pattern for cross-system transfers.

---

## 6. Ignoring Partial Failures

### The Problem
Not handling scenarios where compensation itself fails.

### Why It's Bad
Leaves system in inconsistent state with no retry mechanism, requiring manual intervention.

### Correct Approach
- Retry compensation with exponential backoff
- Dead letter queue for failed compensations
- Alerting for manual intervention
- Make compensation operations more robust than forward operations

---

## 7. Shared Database Anti-Pattern

### The Problem
Using saga pattern while services share a database.

### Why It's Bad
Don't need saga if using shared database - can use local ACID transactions instead. Saga adds unnecessary complexity.

### Correct Approach
Either use local transactions for shared database, or truly separate databases to justify saga pattern.

---

## 8. Forgetting About Isolation

### The Problem
Not handling dirty reads during saga execution. Sagas lack the "I" in ACID.

### Why It's Bad
Other transactions see intermediate state, causing customer confusion and triggering incorrect business logic.

### Correct Approaches
- **Semantic Lock**: Mark records as "PROCESSING" to prevent concurrent access
- **Commutative Updates**: Design operations to be independent of order
- **Pessimistic View**: Hide records until saga completes

---

## 9. Over-Complicated Choreography

### The Problem
Building complex workflows with event choreography, making them impossible to understand.

### Why It's Bad
- No single view of workflow
- Logic scattered across services
- Difficult to debug and monitor
- Hard to evolve

### Correct Approach
Use orchestration for complex workflows. Reserve choreography for simple, linear workflows with 2-3 services.

---

## 10. No Versioning Strategy

### The Problem
Changing saga logic without handling in-flight sagas from old version.

### Why It's Bad
In-flight sagas fail with schema mismatch, cannot roll back deployment safely.

### Correct Approach
- Store saga version with each instance
- Support multiple versions concurrently
- Gradual migration strategy
- Backward-compatible changes when possible

---

## 11. Synchronous Saga Execution

### The Problem
Blocking caller while saga executes, losing the benefits of async processing.

### Why It's Bad
- Poor user experience (long API response times)
- Ties up connection pool
- Cannot scale to handle concurrent requests
- Defeats purpose of distributed architecture

### Correct Approach
Start saga asynchronously, return saga_id immediately, provide status endpoint or webhook callback.

---

## 12. Not Testing Compensations

### The Problem
Only testing happy path, never verifying compensations actually work.

### Why It's Bad
- Compensation bugs discovered in production
- Data corruption from failed rollbacks
- Customer impact (not refunded, etc.)

### Correct Approach
Write tests that simulate failures at each step and verify compensation correctly restores state. Test idempotency of compensations.

---

## Summary: Production Readiness Checklist

Before deploying a saga to production, verify:

- [ ] All operations are idempotent
- [ ] All operations have compensations (or are at the end)
- [ ] Timeouts configured for every step
- [ ] Distributed tracing implemented
- [ ] Metrics and alerts configured
- [ ] Compensation retry logic in place
- [ ] Tested failure scenarios (not just happy path)
- [ ] Dead letter queue for manual intervention
- [ ] Saga versioning strategy in place
- [ ] Async execution (not blocking API calls)
- [ ] Isolation handled (semantic locks, commutative updates)
- [ ] Using right pattern (saga vs ACID transaction)

**If any item is unchecked, reconsider deploying to production.**
