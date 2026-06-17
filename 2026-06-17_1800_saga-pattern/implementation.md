# Saga Pattern Implementation

## Minimal Working Example

### 1. Simple Orchestration (Python)

```python
from enum import Enum
from dataclasses import dataclass
from typing import List, Callable, Optional

class StepStatus(Enum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    COMPENSATED = "compensated"

@dataclass
class SagaStep:
    name: str
    action: Callable
    compensation: Callable
    status: StepStatus = StepStatus.PENDING

class SimpleSagaOrchestrator:
    def __init__(self):
        self.steps: List[SagaStep] = []
        self.completed_steps: List[SagaStep] = []
    
    def add_step(self, name: str, action: Callable, compensation: Callable):
        self.steps.append(SagaStep(name, action, compensation))
    
    def execute(self):
        try:
            # Execute forward steps
            for step in self.steps:
                print(f"Executing: {step.name}")
                step.action()
                step.status = StepStatus.SUCCESS
                self.completed_steps.append(step)
            return True
        except Exception as e:
            print(f"Error: {e}. Starting compensation...")
            self._compensate()
            return False
    
    def _compensate(self):
        # Execute compensations in reverse order
        for step in reversed(self.completed_steps):
            try:
                print(f"Compensating: {step.name}")
                step.compensation()
                step.status = StepStatus.COMPENSATED
            except Exception as e:
                print(f"Compensation failed for {step.name}: {e}")

# Usage Example
def create_order():
    print("  → Order created")

def cancel_order():
    print("  ← Order cancelled")

def reserve_inventory():
    print("  → Inventory reserved")

def release_inventory():
    print("  ← Inventory released")

def process_payment():
    # Simulate payment failure
    raise Exception("Payment declined")

def refund_payment():
    print("  ← Payment refunded")

# Create and execute saga
saga = SimpleSagaOrchestrator()
saga.add_step("Create Order", create_order, cancel_order)
saga.add_step("Reserve Inventory", reserve_inventory, release_inventory)
saga.add_step("Process Payment", process_payment, refund_payment)

success = saga.execute()
print(f"\nSaga completed: {success}")
```

**Output:**
```
Executing: Create Order
  → Order created
Executing: Reserve Inventory
  → Inventory reserved
Executing: Process Payment
Error: Payment declined. Starting compensation...
Compensating: Reserve Inventory
  ← Inventory released
Compensating: Create Order
  ← Order cancelled

Saga completed: False
```

### 2. Event-Driven Choreography (Node.js)

```javascript
const EventEmitter = require('events');

class SagaEventBus extends EventEmitter {}
const eventBus = new SagaEventBus();

// Order Service
class OrderService {
  createOrder(orderId) {
    console.log(`[OrderService] Creating order ${orderId}`);
    const order = { id: orderId, status: 'PENDING' };
    eventBus.emit('OrderCreated', order);
    return order;
  }

  completeOrder(orderId) {
    console.log(`[OrderService] Completing order ${orderId}`);
    eventBus.emit('OrderCompleted', { id: orderId });
  }

  cancelOrder(orderId) {
    console.log(`[OrderService] Cancelling order ${orderId}`);
    eventBus.emit('OrderCancelled', { id: orderId });
  }
}

// Inventory Service
class InventoryService {
  constructor() {
    eventBus.on('OrderCreated', (order) => this.reserveInventory(order));
    eventBus.on('PaymentFailed', (data) => this.releaseInventory(data.orderId));
  }

  reserveInventory(order) {
    console.log(`[InventoryService] Reserving inventory for order ${order.id}`);
    eventBus.emit('InventoryReserved', { orderId: order.id });
  }

  releaseInventory(orderId) {
    console.log(`[InventoryService] Releasing inventory for order ${orderId}`);
    eventBus.emit('InventoryReleased', { orderId });
  }
}

// Payment Service
class PaymentService {
  constructor() {
    eventBus.on('InventoryReserved', (data) => this.processPayment(data.orderId));
  }

  processPayment(orderId) {
    console.log(`[PaymentService] Processing payment for order ${orderId}`);
    
    // Simulate payment failure
    const paymentSuccess = Math.random() > 0.5;
    
    if (paymentSuccess) {
      eventBus.emit('PaymentProcessed', { orderId });
    } else {
      console.log(`[PaymentService] Payment failed for order ${orderId}`);
      eventBus.emit('PaymentFailed', { orderId });
    }
  }
}

// Shipping Service
class ShippingService {
  constructor() {
    eventBus.on('PaymentProcessed', (data) => this.createShipment(data.orderId));
  }

  createShipment(orderId) {
    console.log(`[ShippingService] Creating shipment for order ${orderId}`);
    eventBus.emit('ShipmentCreated', { orderId });
  }
}

// Saga Coordinator (monitors completion)
class SagaCoordinator {
  constructor() {
    eventBus.on('ShipmentCreated', (data) => {
      console.log('\n✓ Saga completed successfully');
      orderService.completeOrder(data.orderId);
    });
    
    eventBus.on('InventoryReleased', (data) => {
      console.log('\n✗ Saga compensated');
      orderService.cancelOrder(data.orderId);
    });
  }
}

// Initialize services
const orderService = new OrderService();
const inventoryService = new InventoryService();
const paymentService = new PaymentService();
const shippingService = new ShippingService();
const coordinator = new SagaCoordinator();

// Start saga
orderService.createOrder('ORDER-123');
```

## Production-Ready Implementation

### Java Spring Boot with Axon Framework

```java
// Saga Definition
@Saga
public class OrderSaga {
    
    @Autowired
    private transient CommandGateway commandGateway;
    
    private String orderId;
    private String inventoryId;
    private String paymentId;
    
    @StartSaga
    @SagaEventHandler(associationProperty = "orderId")
    public void handle(OrderCreatedEvent event) {
        this.orderId = event.getOrderId();
        
        // Reserve inventory
        ReserveInventoryCommand command = new ReserveInventoryCommand(
            UUID.randomUUID().toString(),
            event.getOrderId(),
            event.getProductId(),
            event.getQuantity()
        );
        
        commandGateway.send(command, (commandMessage, commandResultMessage) -> {
            if (commandResultMessage.isExceptional()) {
                // Handle failure - cancel order
                commandGateway.send(new CancelOrderCommand(orderId));
            }
        });
    }
    
    @SagaEventHandler(associationProperty = "orderId")
    public void handle(InventoryReservedEvent event) {
        this.inventoryId = event.getInventoryId();
        
        // Process payment
        ProcessPaymentCommand command = new ProcessPaymentCommand(
            UUID.randomUUID().toString(),
            event.getOrderId(),
            event.getAmount()
        );
        
        commandGateway.send(command, (commandMessage, commandResultMessage) -> {
            if (commandResultMessage.isExceptional()) {
                // Compensate: release inventory
                commandGateway.send(new ReleaseInventoryCommand(inventoryId));
            }
        });
    }
    
    @SagaEventHandler(associationProperty = "orderId")
    public void handle(PaymentProcessedEvent event) {
        this.paymentId = event.getPaymentId();
        
        // Create shipment
        CreateShipmentCommand command = new CreateShipmentCommand(
            UUID.randomUUID().toString(),
            event.getOrderId(),
            event.getShippingAddress()
        );
        
        commandGateway.send(command, (commandMessage, commandResultMessage) -> {
            if (commandResultMessage.isExceptional()) {
                // Compensate: refund payment and release inventory
                commandGateway.send(new RefundPaymentCommand(paymentId));
            }
        });
    }
    
    @SagaEventHandler(associationProperty = "orderId")
    @EndSaga
    public void handle(ShipmentCreatedEvent event) {
        // Complete order
        commandGateway.send(new CompleteOrderCommand(orderId));
    }
    
    // Compensation handlers
    @SagaEventHandler(associationProperty = "orderId")
    public void handle(PaymentFailedEvent event) {
        commandGateway.send(new ReleaseInventoryCommand(inventoryId));
    }
    
    @SagaEventHandler(associationProperty = "orderId")
    @EndSaga
    public void handle(InventoryReleasedEvent event) {
        commandGateway.send(new CancelOrderCommand(orderId));
    }
}

// Order Aggregate
@Aggregate
public class OrderAggregate {
    
    @AggregateIdentifier
    private String orderId;
    private OrderStatus status;
    
    @CommandHandler
    public OrderAggregate(CreateOrderCommand command) {
        AggregateLifecycle.apply(new OrderCreatedEvent(
            command.getOrderId(),
            command.getCustomerId(),
            command.getProductId(),
            command.getQuantity(),
            command.getAmount()
        ));
    }
    
    @EventSourcingHandler
    public void on(OrderCreatedEvent event) {
        this.orderId = event.getOrderId();
        this.status = OrderStatus.PENDING;
    }
    
    @CommandHandler
    public void handle(CompleteOrderCommand command) {
        AggregateLifecycle.apply(new OrderCompletedEvent(command.getOrderId()));
    }
    
    @EventSourcingHandler
    public void on(OrderCompletedEvent event) {
        this.status = OrderStatus.COMPLETED;
    }
    
    @CommandHandler
    public void handle(CancelOrderCommand command) {
        AggregateLifecycle.apply(new OrderCancelledEvent(command.getOrderId()));
    }
    
    @EventSourcingHandler
    public void on(OrderCancelledEvent event) {
        this.status = OrderStatus.CANCELLED;
    }
}
```

### Go Implementation with Temporal

```go
package saga

import (
    "context"
    "time"
    "go.temporal.io/sdk/workflow"
)

// Saga workflow definition
func OrderSagaWorkflow(ctx workflow.Context, order Order) error {
    options := workflow.ActivityOptions{
        StartToCloseTimeout: 10 * time.Second,
    }
    ctx = workflow.WithActivityOptions(ctx, options)
    
    // Compensation stack
    var compensations []func(workflow.Context) error
    
    // Step 1: Create Order
    err := workflow.ExecuteActivity(ctx, CreateOrderActivity, order).Get(ctx, nil)
    if err != nil {
        return err
    }
    compensations = append(compensations, func(ctx workflow.Context) error {
        return workflow.ExecuteActivity(ctx, CancelOrderActivity, order.ID).Get(ctx, nil)
    })
    
    // Step 2: Reserve Inventory
    var inventoryId string
    err = workflow.ExecuteActivity(ctx, ReserveInventoryActivity, order).Get(ctx, &inventoryId)
    if err != nil {
        executeCompensations(ctx, compensations)
        return err
    }
    compensations = append(compensations, func(ctx workflow.Context) error {
        return workflow.ExecuteActivity(ctx, ReleaseInventoryActivity, inventoryId).Get(ctx, nil)
    })
    
    // Step 3: Process Payment
    var paymentId string
    err = workflow.ExecuteActivity(ctx, ProcessPaymentActivity, order).Get(ctx, &paymentId)
    if err != nil {
        executeCompensations(ctx, compensations)
        return err
    }
    compensations = append(compensations, func(ctx workflow.Context) error {
        return workflow.ExecuteActivity(ctx, RefundPaymentActivity, paymentId).Get(ctx, nil)
    })
    
    // Step 4: Create Shipment
    err = workflow.ExecuteActivity(ctx, CreateShipmentActivity, order).Get(ctx, nil)
    if err != nil {
        executeCompensations(ctx, compensations)
        return err
    }
    
    // Step 5: Complete Order
    err = workflow.ExecuteActivity(ctx, CompleteOrderActivity, order.ID).Get(ctx, nil)
    if err != nil {
        executeCompensations(ctx, compensations)
        return err
    }
    
    return nil
}

func executeCompensations(ctx workflow.Context, compensations []func(workflow.Context) error) {
    // Execute in reverse order (LIFO)
    for i := len(compensations) - 1; i >= 0; i-- {
        _ = compensations[i](ctx) // Log errors but continue
    }
}

// Activities (actual service calls)
func CreateOrderActivity(ctx context.Context, order Order) error {
    // Call Order Service
    return orderService.Create(ctx, order)
}

func CancelOrderActivity(ctx context.Context, orderId string) error {
    return orderService.Cancel(ctx, orderId)
}

func ReserveInventoryActivity(ctx context.Context, order Order) (string, error) {
    return inventoryService.Reserve(ctx, order.ProductId, order.Quantity)
}

func ReleaseInventoryActivity(ctx context.Context, inventoryId string) error {
    return inventoryService.Release(ctx, inventoryId)
}

func ProcessPaymentActivity(ctx context.Context, order Order) (string, error) {
    return paymentService.Process(ctx, order.CustomerId, order.Amount)
}

func RefundPaymentActivity(ctx context.Context, paymentId string) error {
    return paymentService.Refund(ctx, paymentId)
}

func CreateShipmentActivity(ctx context.Context, order Order) error {
    return shippingService.CreateShipment(ctx, order)
}

func CompleteOrderActivity(ctx context.Context, orderId string) error {
    return orderService.Complete(ctx, orderId)
}
```

## Common Variations

### 1. Saga with Retry Logic

```python
import time
from tenacity import retry, stop_after_attempt, wait_exponential

class RetryableSaga:
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10)
    )
    def execute_step(self, step: SagaStep):
        try:
            return step.action()
        except TransientError as e:
            print(f"Transient error, will retry: {e}")
            raise
        except PermanentError as e:
            print(f"Permanent error, starting compensation: {e}")
            raise
```

### 2. Saga with Idempotency

```java
@Service
public class IdempotentInventoryService {
    
    @Autowired
    private IdempotencyStore idempotencyStore;
    
    public String reserveInventory(String idempotencyKey, ReservationRequest request) {
        // Check if already processed
        Optional<String> existingResult = idempotencyStore.get(idempotencyKey);
        if (existingResult.isPresent()) {
            return existingResult.get(); // Return cached result
        }
        
        // Process reservation
        String reservationId = performReservation(request);
        
        // Store result
        idempotencyStore.put(idempotencyKey, reservationId, Duration.ofHours(24));
        
        return reservationId;
    }
}
```

### 3. Saga with Timeout Handling

```typescript
class TimeoutSaga {
  async executeWithTimeout(step: SagaStep, timeoutMs: number): Promise<void> {
    const timeoutPromise = new Promise((_, reject) => {
      setTimeout(() => reject(new TimeoutError(`Step ${step.name} timed out`)), timeoutMs);
    });
    
    try {
      await Promise.race([step.action(), timeoutPromise]);
    } catch (error) {
      if (error instanceof TimeoutError) {
        console.log(`Timeout on ${step.name}, compensating...`);
        await this.compensate();
      }
      throw error;
    }
  }
}
```

### 4. Saga with Semantic Lock

```python
class SemanticLockSaga:
    def __init__(self, db):
        self.db = db
    
    def execute_order_saga(self, order_id: str):
        # Acquire semantic lock by marking order as PROCESSING
        updated = self.db.update_order_status(
            order_id,
            new_status='PROCESSING',
            expected_status='PENDING'  # Optimistic locking
        )
        
        if not updated:
            raise ConcurrentModificationError("Order already being processed")
        
        try:
            # Execute saga steps
            self.reserve_inventory(order_id)
            self.process_payment(order_id)
            self.create_shipment(order_id)
            
            # Release lock by completing
            self.db.update_order_status(order_id, 'COMPLETED')
        except Exception as e:
            # Compensate and mark as failed
            self.compensate()
            self.db.update_order_status(order_id, 'FAILED')
            raise
```

### 5. Parallel Saga Steps

```go
func ParallelSagaWorkflow(ctx workflow.Context, order Order) error {
    // Execute independent steps in parallel
    var futures []workflow.Future
    
    // Parallel execution
    futures = append(futures, 
        workflow.ExecuteActivity(ctx, ValidateInventoryActivity, order))
    futures = append(futures, 
        workflow.ExecuteActivity(ctx, ValidateCustomerCreditActivity, order))
    futures = append(futures, 
        workflow.ExecuteActivity(ctx, CheckFraudActivity, order))
    
    // Wait for all to complete
    for _, future := range futures {
        if err := future.Get(ctx, nil); err != nil {
            return err
        }
    }
    
    // Continue with sequential steps
    return executeSequentialSteps(ctx, order)
}
```

## Testing Strategies

### Unit Testing Saga Logic

```python
import unittest
from unittest.mock import Mock

class TestOrderSaga(unittest.TestCase):
    def setUp(self):
        self.saga = OrderSaga()
        self.order_service = Mock()
        self.inventory_service = Mock()
        self.payment_service = Mock()
        
    def test_successful_saga(self):
        # Arrange
        self.inventory_service.reserve.return_value = "INV-123"
        self.payment_service.process.return_value = "PAY-456"
        
        # Act
        result = self.saga.execute("ORDER-789")
        
        # Assert
        self.assertTrue(result)
        self.order_service.create.assert_called_once()
        self.inventory_service.reserve.assert_called_once()
        self.payment_service.process.assert_called_once()
        
    def test_payment_failure_triggers_compensation(self):
        # Arrange
        self.inventory_service.reserve.return_value = "INV-123"
        self.payment_service.process.side_effect = PaymentError("Declined")
        
        # Act
        result = self.saga.execute("ORDER-789")
        
        # Assert
        self.assertFalse(result)
        self.inventory_service.release.assert_called_once_with("INV-123")
        self.order_service.cancel.assert_called_once()
```

### Integration Testing

```java
@SpringBootTest
@TestPropertySource(locations = "classpath:test.properties")
public class OrderSagaIntegrationTest {
    
    @Autowired
    private SagaManager sagaManager;
    
    @Autowired
    private OrderRepository orderRepository;
    
    @Test
    public void testSuccessfulOrderSaga() throws Exception {
        // Given
        CreateOrderCommand command = new CreateOrderCommand(
            UUID.randomUUID().toString(),
            "CUSTOMER-1",
            "PRODUCT-1",
            2,
            new BigDecimal("99.99")
        );
        
        // When
        CommandMessage<?> result = sagaManager.execute(command).get(5, TimeUnit.SECONDS);
        
        // Then
        Order order = orderRepository.findById(command.getOrderId()).get();
        assertThat(order.getStatus()).isEqualTo(OrderStatus.COMPLETED);
    }
    
    @Test
    public void testPaymentFailureCompensation() throws Exception {
        // Given - payment service configured to fail
        mockPaymentService.setFailureMode(true);
        
        CreateOrderCommand command = new CreateOrderCommand(/*...*/);
        
        // When
        CommandMessage<?> result = sagaManager.execute(command).get(5, TimeUnit.SECONDS);
        
        // Then
        Order order = orderRepository.findById(command.getOrderId()).get();
        assertThat(order.getStatus()).isEqualTo(OrderStatus.CANCELLED);
        
        // Verify compensations
        verify(inventoryService).release(anyString());
        verify(orderService).cancel(anyString());
    }
}
```

## Deployment Considerations

### Kubernetes Configuration

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: saga-orchestrator
spec:
  replicas: 3
  selector:
    matchLabels:
      app: saga-orchestrator
  template:
    metadata:
      labels:
        app: saga-orchestrator
    spec:
      containers:
      - name: orchestrator
        image: saga-orchestrator:1.0
        env:
        - name: DB_CONNECTION
          valueFrom:
            secretKeyRef:
              name: saga-db-secret
              key: connection-string
        resources:
          requests:
            memory: "256Mi"
            cpu: "250m"
          limits:
            memory: "512Mi"
            cpu: "500m"
        livenessProbe:
          httpGet:
            path: /health
            port: 8080
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /ready
            port: 8080
          initialDelaySeconds: 5
          periodSeconds: 5
```

## Performance Optimization

### Database Indexing

```sql
-- Saga instance table
CREATE TABLE saga_instances (
    id VARCHAR(255) PRIMARY KEY,
    saga_type VARCHAR(100) NOT NULL,
    status VARCHAR(50) NOT NULL,
    current_step INT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_status (status),
    INDEX idx_created_at (created_at),
    INDEX idx_type_status (saga_type, status)
);

-- Idempotency store
CREATE TABLE idempotency_keys (
    key VARCHAR(255) PRIMARY KEY,
    result TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL,
    INDEX idx_expires_at (expires_at)
);
```

### Caching Strategy

```python
from functools import lru_cache
import redis

class SagaCache:
    def __init__(self):
        self.redis = redis.Redis(host='localhost', port=6379, db=0)
    
    def get_saga_state(self, saga_id: str):
        cached = self.redis.get(f"saga:{saga_id}")
        if cached:
            return json.loads(cached)
        return None
    
    def set_saga_state(self, saga_id: str, state: dict, ttl: int = 3600):
        self.redis.setex(
            f"saga:{saga_id}",
            ttl,
            json.dumps(state)
        )
```

## Monitoring and Observability

### Distributed Tracing

```java
@Component
public class TracedSagaExecutor {
    
    @Autowired
    private Tracer tracer;
    
    public void executeSaga(Saga saga) {
        Span span = tracer.buildSpan("saga-execution")
            .withTag("saga.id", saga.getId())
            .withTag("saga.type", saga.getType())
            .start();
        
        try (Scope scope = tracer.scopeManager().activate(span)) {
            saga.execute();
            span.setTag("saga.status", "completed");
        } catch (Exception e) {
            span.setTag("saga.status", "failed");
            span.log(Collections.singletonMap("error", e.getMessage()));
            throw e;
        } finally {
            span.finish();
        }
    }
}
```

### Metrics Collection

```python
from prometheus_client import Counter, Histogram, Gauge

saga_started = Counter('saga_started_total', 'Total sagas started', ['saga_type'])
saga_completed = Counter('saga_completed_total', 'Total sagas completed', ['saga_type'])
saga_failed = Counter('saga_failed_total', 'Total sagas failed', ['saga_type', 'failure_reason'])
saga_duration = Histogram('saga_duration_seconds', 'Saga execution time', ['saga_type'])
active_sagas = Gauge('saga_active', 'Currently active sagas', ['saga_type'])

class MonitoredSaga:
    def execute(self):
        saga_started.labels(saga_type=self.type).inc()
        active_sagas.labels(saga_type=self.type).inc()
        
        with saga_duration.labels(saga_type=self.type).time():
            try:
                self._execute_steps()
                saga_completed.labels(saga_type=self.type).inc()
            except Exception as e:
                saga_failed.labels(
                    saga_type=self.type,
                    failure_reason=type(e).__name__
                ).inc()
                raise
            finally:
                active_sagas.labels(saga_type=self.type).dec()
```

## Summary

This implementation guide covers:
- **Minimal examples** for quick prototyping
- **Production-ready** implementations with popular frameworks
- **Common variations** for real-world scenarios
- **Testing strategies** for reliability
- **Performance optimization** for scale
- **Monitoring** for operational excellence

Choose the implementation approach that matches your team's technology stack and operational maturity.
