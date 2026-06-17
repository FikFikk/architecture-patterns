# Saga Pattern

## Overview

The Saga Pattern is a distributed transaction pattern that manages data consistency across microservices without requiring distributed ACID transactions. It breaks a large transaction into a sequence of local transactions, each updating a single service, with compensating transactions to handle failures.

## The Problem It Solves

### Challenge: Distributed Transactions in Microservices

In a microservices architecture, each service has its own database (database-per-service pattern). Traditional distributed transactions using two-phase commit (2PC) become impractical because:

1. **Tight Coupling**: Services must coordinate through a transaction coordinator
2. **Reduced Availability**: All services must be available for the transaction to proceed
3. **Lock Contention**: Resources are locked across multiple services, reducing throughput
4. **Technology Constraints**: NoSQL databases often don't support 2PC
5. **Long-Running Processes**: Business processes spanning hours/days can't hold locks

### Example Scenario: E-Commerce Order

When a customer places an order:
1. Reserve inventory in the Inventory Service
2. Process payment in the Payment Service
3. Create shipment in the Shipping Service
4. Update loyalty points in the Customer Service

If payment fails after inventory is reserved, how do you maintain consistency without a distributed transaction?

## How Saga Pattern Works

A saga is a sequence of local transactions where:
- Each local transaction updates the database and publishes an event/message
- If a local transaction fails, the saga executes compensating transactions to undo changes
- Compensating transactions are idempotent and must semantically reverse the effect

### Two Implementation Approaches

**1. Choreography (Event-Based)**
- Services publish events when local transactions complete
- Other services listen to events and trigger their local transactions
- Decentralized coordination
- No single point of failure

**2. Orchestration (Command-Based)**
- Central orchestrator tells services what operations to execute
- Orchestrator manages the saga workflow and compensations
- Centralized coordination and monitoring
- Easier to understand and debug

## Core Concepts

### Forward Recovery (Retry)
Continue the saga by retrying failed steps. Works when failures are transient.

### Backward Recovery (Compensate)
Undo completed steps by executing compensating transactions in reverse order.

### Semantic Lock
Application-level lock preventing concurrent sagas from interfering (e.g., marking an order as "PENDING" to prevent modifications).

### Idempotency
Each transaction and compensating transaction must be safely retryable without side effects.

## Key Benefits

1. **Maintains Eventual Consistency**: Without distributed locks
2. **High Availability**: Services remain loosely coupled
3. **Scalability**: No central transaction coordinator bottleneck (in choreography)
4. **Flexibility**: Supports long-running business processes
5. **Technology Agnostic**: Works with any database (SQL, NoSQL)

## Trade-offs

### Advantages
- No distributed locking
- Better scalability and availability
- Supports heterogeneous technology stacks
- Natural fit for event-driven architectures

### Disadvantages
- **Complexity**: More complex than ACID transactions
- **Eventual Consistency**: Not immediately consistent (ACI without D)
- **Lack of Isolation**: Dirty reads possible (compensations might be visible)
- **Debugging Difficulty**: Distributed tracing required
- **Compensation Logic**: Must design reversible operations

## When to Use

Use Saga Pattern when:
- You have a microservices architecture with database-per-service
- You need to maintain data consistency across services
- Eventual consistency is acceptable for your use case
- Business processes span multiple services
- Long-running transactions (seconds to days)
- You want to avoid distributed locks and 2PC

See [when-to-use.md](./when-to-use.md) for detailed decision criteria.

## Real-World Adoption

- **Netflix**: Order fulfillment and billing
- **Uber**: Trip management and payments
- **Amazon**: Order processing
- **Airbnb**: Booking workflows
- **Microsoft**: Azure Durable Functions

See [real-world-examples.md](./real-world-examples.md) for implementation details.

## References

- [Microservices Patterns](https://microservices.io/patterns/data/saga.html) by Chris Richardson
- Original paper: [Sagas (1987)](https://www.cs.cornell.edu/andru/cs711/2002fa/reading/sagas.pdf) by Hector Garcia-Molina and Kenneth Salem
- [Designing Data-Intensive Applications](https://dataintensive.net/) by Martin Kleppmann (Chapter 9)
- [Enterprise Integration Patterns](https://www.enterpriseintegrationpatterns.com/) by Gregor Hohpe

## See Also

- [when-to-use.md](./when-to-use.md) - Detailed use cases and decision criteria
- [diagram.md](./diagram.md) - Architecture diagrams
- [implementation.md](./implementation.md) - Code examples
- [anti-patterns.md](./anti-patterns.md) - Common mistakes
- [evolution.md](./evolution.md) - Pattern evolution and alternatives
