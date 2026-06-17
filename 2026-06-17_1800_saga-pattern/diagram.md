# Saga Pattern Architecture Diagrams

## 1. High-Level Saga Flow

### Choreography-Based Saga (Event-Driven)

```mermaid
sequenceDiagram
    participant Client
    participant OrderService
    participant InventoryService
    participant PaymentService
    participant ShippingService
    participant MessageBroker

    Client->>OrderService: Create Order
    OrderService->>OrderService: Create Order (PENDING)
    OrderService->>MessageBroker: OrderCreated Event
    
    MessageBroker->>InventoryService: OrderCreated Event
    InventoryService->>InventoryService: Reserve Inventory
    InventoryService->>MessageBroker: InventoryReserved Event
    
    MessageBroker->>PaymentService: InventoryReserved Event
    PaymentService->>PaymentService: Process Payment
    PaymentService->>MessageBroker: PaymentProcessed Event
    
    MessageBroker->>ShippingService: PaymentProcessed Event
    ShippingService->>ShippingService: Create Shipment
    ShippingService->>MessageBroker: ShipmentCreated Event
    
    MessageBroker->>OrderService: ShipmentCreated Event
    OrderService->>OrderService: Update Order (COMPLETED)
    OrderService->>Client: Order Completed
```

### Orchestration-Based Saga (Command-Driven)

```mermaid
sequenceDiagram
    participant Client
    participant Orchestrator
    participant OrderService
    participant InventoryService
    participant PaymentService
    participant ShippingService

    Client->>Orchestrator: Create Order Request
    Orchestrator->>OrderService: Create Order
    OrderService-->>Orchestrator: Order Created (PENDING)
    
    Orchestrator->>InventoryService: Reserve Inventory
    InventoryService-->>Orchestrator: Inventory Reserved
    
    Orchestrator->>PaymentService: Process Payment
    PaymentService-->>Orchestrator: Payment Processed
    
    Orchestrator->>ShippingService: Create Shipment
    ShippingService-->>Orchestrator: Shipment Created
    
    Orchestrator->>OrderService: Complete Order
    OrderService-->>Orchestrator: Order Completed
    Orchestrator-->>Client: Success Response
```

## 2. Compensation Flow (Rollback)

### Successful Path vs. Failed Path

```mermaid
graph LR
    subgraph "Happy Path"
    A1[Create Order] --> B1[Reserve Inventory]
    B1 --> C1[Process Payment]
    C1 --> D1[Create Shipment]
    D1 --> E1[Complete Order]
    end
    
    subgraph "Failure & Compensation"
    A2[Create Order] --> B2[Reserve Inventory]
    B2 --> C2[Process Payment]
    C2 --> X[Payment Failed ❌]
    X --> C3[Skip Refund]
    C3 --> B3[Release Inventory]
    B3 --> A3[Cancel Order]
    end
```

### Detailed Compensation Sequence

```mermaid
sequenceDiagram
    participant Orchestrator
    participant OrderService
    participant InventoryService
    participant PaymentService
    participant ShippingService

    Orchestrator->>OrderService: Create Order
    OrderService-->>Orchestrator: ✓ Order Created
    
    Orchestrator->>InventoryService: Reserve Inventory
    InventoryService-->>Orchestrator: ✓ Inventory Reserved
    
    Orchestrator->>PaymentService: Process Payment
    PaymentService-->>Orchestrator: ❌ Payment Failed
    
    Note over Orchestrator: Start Compensation
    
    Orchestrator->>InventoryService: Release Inventory (Compensate)
    InventoryService-->>Orchestrator: ✓ Inventory Released
    
    Orchestrator->>OrderService: Cancel Order (Compensate)
    OrderService-->>Orchestrator: ✓ Order Cancelled
    
    Orchestrator-->>Client: Order Failed (Rolled Back)
```

## 3. State Machine View

### Order Saga State Transitions

```mermaid
stateDiagram-v2
    [*] --> OrderPending: Create Order
    
    OrderPending --> InventoryReserved: Reserve Inventory
    OrderPending --> OrderCancelled: Create Failed
    
    InventoryReserved --> PaymentProcessed: Process Payment
    InventoryReserved --> CompensateInventory: Payment Failed
    
    PaymentProcessed --> ShipmentCreated: Create Shipment
    PaymentProcessed --> CompensatePayment: Shipment Failed
    
    ShipmentCreated --> OrderCompleted: Complete Order
    
    CompensatePayment --> CompensateInventory: Refund Complete
    CompensateInventory --> OrderCancelled: Release Complete
    
    OrderCompleted --> [*]
    OrderCancelled --> [*]
```

## 4. Choreography Architecture

### Event-Driven Microservices

```
                    ┌─────────────────────┐
                    │   Message Broker    │
                    │   (Kafka/RabbitMQ)  │
                    └──────────┬──────────┘
                               │
        ┌──────────────────────┼──────────────────────┐
        │                      │                      │
        ▼                      ▼                      ▼
┌───────────────┐      ┌───────────────┐     ┌───────────────┐
│ Order Service │      │   Inventory   │     │    Payment    │
│               │      │    Service    │     │    Service    │
├───────────────┤      ├───────────────┤     ├───────────────┤
│ - Create      │      │ - Reserve     │     │ - Process     │
│ - Complete    │      │ - Release     │     │ - Refund      │
│ - Cancel      │      │               │     │               │
└───────┬───────┘      └───────┬───────┘     └───────┬───────┘
        │                      │                     │
        │ OrderCreated         │ InventoryReserved   │ PaymentProcessed
        └──────────────────────┴─────────────────────┘
                               │
                               ▼
                       ┌───────────────┐
                       │   Shipping    │
                       │    Service    │
                       ├───────────────┤
                       │ - Create      │
                       │ - Cancel      │
                       └───────────────┘

Events Flow:
1. OrderCreated → Inventory listens
2. InventoryReserved → Payment listens
3. PaymentProcessed → Shipping listens
4. ShipmentCreated → Order listens
```

### Choreography Event Flow (ASCII)

```
Time →

OrderService:     [Create]──→[Wait]──────────────→[Complete]
                     │                               ▲
                     │OrderCreated                   │ShipmentCreated
                     ▼                               │
InventoryService:  [Wait]──→[Reserve]──→[Wait]──────┤
                               │                     │
                               │InventoryReserved    │
                               ▼                     │
PaymentService:             [Wait]──→[Process]──→[Wait]
                                        │            │
                                        │PaymentProcessed
                                        ▼            │
ShippingService:                     [Wait]──→[Create]──┘
```

## 5. Orchestration Architecture

### Centralized Orchestrator

```
                    ┌─────────────────────────┐
                    │   Saga Orchestrator     │
                    │  (Workflow Engine)      │
                    │                         │
                    │  State Machine:         │
                    │  - Current Step         │
                    │  - Compensation Stack   │
                    │  - Retry Logic          │
                    └────────┬────────────────┘
                             │
             ┌───────────────┼───────────────┐
             │               │               │
    Command  │      Command  │      Command  │
             ▼               ▼               ▼
    ┌────────────┐  ┌────────────┐  ┌────────────┐
    │   Order    │  │ Inventory  │  │  Payment   │
    │  Service   │  │  Service   │  │  Service   │
    └────────────┘  └────────────┘  └────────────┘
             │               │               │
    Response │      Response │      Response │
             └───────────────┴───────────────┘
                             │
                             ▼
                    ┌────────────┐
                    │  Shipping  │
                    │  Service   │
                    └────────────┘
```

### Orchestrator Internal Logic

```
┌──────────────────────────────────────────────┐
│         Saga Orchestrator                    │
│                                              │
│  ┌────────────────────────────────────┐     │
│  │      Saga Definition               │     │
│  │  1. Create Order                   │     │
│  │  2. Reserve Inventory              │     │
│  │  3. Process Payment                │     │
│  │  4. Create Shipment                │     │
│  │  5. Complete Order                 │     │
│  └────────────────────────────────────┘     │
│                                              │
│  ┌────────────────────────────────────┐     │
│  │   Compensation Stack (LIFO)        │     │
│  │  [Cancel Shipment]      ← Step 4   │     │
│  │  [Refund Payment]       ← Step 3   │     │
│  │  [Release Inventory]    ← Step 2   │     │
│  │  [Cancel Order]         ← Step 1   │     │
│  └────────────────────────────────────┘     │
│                                              │
│  ┌────────────────────────────────────┐     │
│  │      Saga Instance State           │     │
│  │  ID: saga-12345                    │     │
│  │  Current Step: 3                   │     │
│  │  Status: IN_PROGRESS               │     │
│  │  Started: 2026-06-17T10:00:00Z     │     │
│  │  Retries: 0                        │     │
│  └────────────────────────────────────┘     │
└──────────────────────────────────────────────┘
```

## 6. Data Flow Diagram

### Complete Saga Execution

```mermaid
flowchart TD
    Start([Client Request]) --> CreateOrder[Create Order]
    CreateOrder --> |Success| ReserveInventory[Reserve Inventory]
    CreateOrder --> |Failure| End1([Return Error])
    
    ReserveInventory --> |Success| ProcessPayment[Process Payment]
    ReserveInventory --> |Failure| CancelOrder[Cancel Order]
    
    ProcessPayment --> |Success| CreateShipment[Create Shipment]
    ProcessPayment --> |Failure| ReleaseInventory[Release Inventory]
    
    CreateShipment --> |Success| CompleteOrder[Complete Order]
    CreateShipment --> |Failure| RefundPayment[Refund Payment]
    
    CompleteOrder --> End2([Success])
    
    RefundPayment --> ReleaseInventory
    ReleaseInventory --> CancelOrder
    CancelOrder --> End3([Compensated])
    
    style CreateOrder fill:#90EE90
    style ReserveInventory fill:#90EE90
    style ProcessPayment fill:#90EE90
    style CreateShipment fill:#90EE90
    style CompleteOrder fill:#90EE90
    
    style CancelOrder fill:#FFB6C1
    style ReleaseInventory fill:#FFB6C1
    style RefundPayment fill:#FFB6C1
```

## 7. Component Architecture

### System Overview

```
┌────────────────────────────────────────────────────────────┐
│                         Client Layer                       │
│              (Web App, Mobile App, API Gateway)            │
└────────────────────┬───────────────────────────────────────┘
                     │
                     ▼
┌────────────────────────────────────────────────────────────┐
│                   Saga Orchestrator Layer                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐    │
│  │ Saga Manager │  │ State Store  │  │ Event Logger │    │
│  └──────────────┘  └──────────────┘  └──────────────┘    │
└────────────────────┬───────────────────────────────────────┘
                     │
    ┌────────────────┼────────────────┬────────────────┐
    │                │                │                │
    ▼                ▼                ▼                ▼
┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐
│ Order   │    │Inventory│    │ Payment │    │Shipping │
│ Service │    │ Service │    │ Service │    │ Service │
├─────────┤    ├─────────┤    ├─────────┤    ├─────────┤
│ DB      │    │ DB      │    │ DB      │    │ DB      │
└─────────┘    └─────────┘    └─────────┘    └─────────┘
```

## 8. Retry and Timeout Handling

### Retry Logic Flow

```mermaid
graph TD
    A[Execute Step] --> B{Success?}
    B -->|Yes| C[Next Step]
    B -->|No| D{Retriable?}
    D -->|Yes| E{Retry Count < Max?}
    D -->|No| F[Start Compensation]
    E -->|Yes| G[Wait with Backoff]
    E -->|No| F
    G --> A
    C --> H[Continue Saga]
    F --> I[Rollback Saga]
    
    style A fill:#87CEEB
    style C fill:#90EE90
    style F fill:#FFB6C1
    style I fill:#FFB6C1
```

### Timeout Configuration

```
Step Configuration:
┌────────────────────────────────────┐
│ Step: Reserve Inventory            │
│ Timeout: 5s                        │
│ Max Retries: 3                     │
│ Backoff: Exponential (1s, 2s, 4s) │
│ Idempotency Key: saga-id + step-id │
└────────────────────────────────────┘

┌────────────────────────────────────┐
│ Step: Process Payment              │
│ Timeout: 30s                       │
│ Max Retries: 1                     │
│ Backoff: None                      │
│ Idempotency Key: saga-id + step-id │
└────────────────────────────────────┘
```

## 9. Monitoring and Observability

### Distributed Tracing

```
Trace ID: trace-abc123
├─ Span: CreateOrder [OrderService]
│  ├─ Duration: 50ms
│  └─ Status: SUCCESS
├─ Span: ReserveInventory [InventoryService]
│  ├─ Duration: 120ms
│  ├─ Status: SUCCESS
│  └─ Tags: product_id=456, quantity=2
├─ Span: ProcessPayment [PaymentService]
│  ├─ Duration: 350ms
│  ├─ Status: FAILED
│  └─ Error: Insufficient funds
└─ Span: ReleaseInventory [InventoryService] (Compensation)
   ├─ Duration: 80ms
   └─ Status: SUCCESS

Total Duration: 600ms
Result: COMPENSATED
```

### Saga Dashboard View

```
┌─────────────────────────────────────────────────┐
│           Saga Monitoring Dashboard             │
├─────────────────────────────────────────────────┤
│ Active Sagas: 247                               │
│ Completed (24h): 12,453                         │
│ Failed (24h): 127 (1.02%)                       │
│ Compensated (24h): 89 (0.71%)                   │
├─────────────────────────────────────────────────┤
│ Average Duration:                               │
│  ▓▓▓▓▓▓▓▓▓░░░ 1.2s                             │
│                                                 │
│ Step Success Rate:                              │
│  Create Order:     █████████████████ 99.8%     │
│  Reserve Inventory: ████████████████ 99.2%     │
│  Process Payment:  ██████████████░░ 97.8%      │
│  Create Shipment:  █████████████████ 99.5%     │
├─────────────────────────────────────────────────┤
│ Recent Failures:                                │
│  • saga-789: Payment timeout (compensated)      │
│  • saga-790: Inventory unavailable (compensated)│
└─────────────────────────────────────────────────┘
```

## 10. Comparison: Choreography vs Orchestration

```
┌─────────────────────────────────────────────────────────────┐
│                    Choreography                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Service A ──Event──→ Service B ──Event──→ Service C       │
│     ↑                     │                     │           │
│     │                     Event                 Event       │
│     └─────────────────────┴─────────────────────┘           │
│                                                             │
│  ✓ Decentralized                                            │
│  ✓ No single point of failure                              │
│  ✗ Harder to understand workflow                           │
│  ✗ Distributed monitoring required                         │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                    Orchestration                            │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│                  ┌──────────────┐                           │
│                  │ Orchestrator │                           │
│                  └───┬────┬────┬┘                           │
│                      │    │    │                            │
│                 Cmd  │Cmd │Cmd │                            │
│                      ▼    ▼    ▼                            │
│                   Svc A Svc B Svc C                         │
│                                                             │
│  ✓ Centralized workflow logic                              │
│  ✓ Easy to monitor and debug                               │
│  ✗ Single point of failure                                 │
│  ✗ Orchestrator becomes bottleneck                         │
└─────────────────────────────────────────────────────────────┘
```

## Conclusion

These diagrams illustrate:
- **Choreography**: Decentralized, event-driven coordination
- **Orchestration**: Centralized, command-driven coordination
- **Compensation**: Backward recovery via reverse transactions
- **State Management**: Tracking saga progress and rollback
- **Monitoring**: Observability through distributed tracing

Choose the architecture that fits your team's operational capabilities and system complexity.
