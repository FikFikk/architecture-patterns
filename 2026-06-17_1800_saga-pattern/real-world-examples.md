# Real-World Examples of Saga Pattern

## 1. Netflix - Order Fulfillment and Billing

### Use Case
Netflix uses saga pattern for subscription management and billing workflows spanning multiple services.

### Architecture
- **Subscription Service**: Manages plan changes
- **Billing Service**: Processes payments
- **Entitlement Service**: Grants/revokes access
- **Notification Service**: Sends confirmations

### Implementation Approach
**Orchestration-based** using internal workflow engine.

### Saga Flow
1. Customer upgrades to Premium plan
2. Subscription Service creates pending upgrade
3. Billing Service processes pro-rated charge
4. If payment succeeds → Entitlement Service grants Premium features
5. If payment fails → Revert subscription to previous plan

### Key Learnings
- **Idempotency critical**: Customers may retry failed upgrades
- **Partial failures**: Payment succeeds but entitlement fails → refund saga
- **Timing windows**: Must handle users streaming during upgrade

### Technical Stack
- Custom workflow orchestrator
- Apache Kafka for event streaming
- Cassandra for saga state persistence

### Reference
- [Netflix Tech Blog - Orchestration vs Choreography](https://netflixtechblog.com/)

---

## 2. Uber - Trip Management and Payments

### Use Case
Managing ride lifecycle from request to completion and payment settlement.

### Architecture
- **Trip Service**: Manages ride state
- **Driver Service**: Driver availability and assignment
- **Pricing Service**: Calculates fares
- **Payment Service**: Processes rider charges and driver payouts
- **Location Service**: Tracks GPS coordinates

### Implementation Approach
**Choreography-based** using event-driven architecture.

### Saga Flow
**Happy Path:**
1. Rider requests trip → TripRequested event
2. Driver Service finds driver → DriverAssigned event
3. Trip starts → TripStarted event
4. Trip ends → TripCompleted event
5. Pricing calculates fare → FareCalculated event
6. Payment charges rider → RiderCharged event
7. Payment settles with driver → DriverPaid event

**Cancellation Saga:**
- Rider cancels before pickup → Cancel driver assignment, apply cancellation fee
- Driver unavailable after assignment → Find new driver or refund rider

### Key Learnings
- **Real-time requirements**: Sub-second latency for driver assignment
- **Geo-distributed**: Sagas span multiple regions
- **High volume**: Millions of trips daily require efficient saga management
- **Compensations complex**: Cancellation policies vary by region and timing

### Technical Stack
- Apache Kafka for event streaming
- Cassandra and PostgreSQL for persistence
- Custom saga framework built on Cadence (now Temporal)

### Challenges
- **Network partitions**: Handling split-brain scenarios
- **Exactly-once processing**: Preventing double charges
- **Surge pricing**: Dynamic fare calculations during saga execution

### Reference
- [Uber Engineering Blog - Cadence](https://eng.uber.com/cadence/)

---

## 3. Amazon - Order Processing

### Use Case
E-commerce order fulfillment from checkout to delivery.

### Architecture
- **Order Service**: Order lifecycle management
- **Inventory Service**: Stock management across warehouses
- **Payment Service**: Payment processing
- **Fulfillment Service**: Picking, packing, shipping
- **Delivery Service**: Last-mile delivery tracking
- **Notification Service**: Customer communications

### Implementation Approach
**Hybrid**: Orchestration for critical path, choreography for ancillary services.

### Saga Flow
**Orchestrated Core:**
1. Create order (PENDING)
2. Reserve inventory across warehouses
3. Process payment
4. Create fulfillment task
5. Complete order (CONFIRMED)

**Choreographed Ancillary:**
- Notification service listens to order events
- Analytics service updates dashboards
- Recommendation service adjusts models

### Key Learnings
- **Multi-warehouse complexity**: Saga coordinates inventory from multiple locations
- **Partial shipments**: Split orders require nested sagas
- **Prime delivery SLA**: Time constraints on saga execution
- **Return handling**: Reverse sagas for order returns

### Compensation Strategies
- Payment failure → Release all inventory reservations
- Fulfillment failure → Refund payment, release inventory
- Delivery failure → Trigger replacement order saga

### Technical Stack
- AWS Step Functions for orchestration
- Amazon SQS/SNS for messaging
- DynamoDB for saga state
- Custom retry and backoff logic

### Scale
- Processes millions of orders daily
- Peak traffic (Prime Day) requires elastic saga execution
- Global distribution across regions

### Reference
- [AWS Step Functions Use Cases](https://aws.amazon.com/step-functions/)

---

## 4. Airbnb - Booking Workflow

### Use Case
Coordinating reservation between guest, host, and payment processing.

### Architecture
- **Booking Service**: Manages reservation state
- **Availability Service**: Calendar management
- **Payment Service**: Processes guest payment and host payout
- **Messaging Service**: Guest-host communication
- **Trust & Safety Service**: Fraud detection
- **Pricing Service**: Dynamic pricing and currency conversion

### Implementation Approach
**Orchestration-based** with human-in-the-loop steps.

### Saga Flow
1. Guest requests booking → PENDING
2. Block calendar dates (soft lock)
3. Hold payment (authorize, don't capture)
4. **Manual step**: Host approves/declines (24-48 hour timeout)
5. If approved:
   - Capture payment
   - Confirm calendar block
   - Notify guest → CONFIRMED
6. If declined or timeout:
   - Release payment hold
   - Unblock calendar
   - Notify guest → DECLINED

### Key Learnings
- **Long-running sagas**: Can span days waiting for host approval
- **Human decisions**: Cannot force saga completion, must handle timeouts gracefully
- **Currency complexity**: Multi-currency transactions with exchange rate fluctuations
- **Regulatory compliance**: Different rules per country (taxes, local laws)

### Compensation Challenges
- **Cancellation policies**: Vary by host settings (flexible, moderate, strict)
- **Service fees**: Non-refundable portions on cancellation
- **Host payouts**: Scheduled releases require coordination

### Technical Stack
- Custom orchestration engine
- MySQL for transactional data
- Redis for distributed locks
- Kafka for event streaming

### Reference
- [Airbnb Engineering Blog](https://medium.com/airbnb-engineering)

---

## 5. Microsoft Azure - Durable Functions

### Use Case
Platform-as-a-Service for building saga patterns without custom infrastructure.

### What It Provides
Built-in saga orchestration as a service:
- Automatic state persistence
- Retry logic
- Timeout handling
- Compensation support
- Visual workflow monitoring

### Example: E-Commerce Saga

```csharp
[FunctionName("OrderSaga")]
public static async Task<bool> RunOrchestrator(
    [OrchestrationTrigger] IDurableOrchestrationContext context)
{
    var order = context.GetInput<Order>();
    
    try
    {
        // Forward transactions
        await context.CallActivityAsync("CreateOrder", order);
        var inventoryId = await context.CallActivityAsync<string>("ReserveInventory", order);
        var paymentId = await context.CallActivityAsync<string>("ProcessPayment", order);
        await context.CallActivityAsync("CreateShipment", order);
        await context.CallActivityAsync("CompleteOrder", order.Id);
        
        return true;
    }
    catch (Exception)
    {
        // Compensating transactions
        await context.CallActivityAsync("CancelShipment", order.Id);
        await context.CallActivityAsync("RefundPayment", paymentId);
        await context.CallActivityAsync("ReleaseInventory", inventoryId);
        await context.CallActivityAsync("CancelOrder", order.Id);
        
        return false;
    }
}
```

### Who Uses It
- Companies building on Azure without dedicated saga infrastructure
- Startups needing quick time-to-market
- Teams without distributed systems expertise

### Key Benefits
- **No infrastructure management**: Serverless execution
- **Built-in resilience**: Automatic retries and checkpointing
- **Language support**: C#, JavaScript, Python, Java, PowerShell

### Limitations
- **Vendor lock-in**: Azure-specific
- **Cost**: Per-execution pricing can add up at scale
- **Cold starts**: Serverless latency for infrequent sagas

### Reference
- [Azure Durable Functions Documentation](https://docs.microsoft.com/azure/azure-functions/durable/)

---

## 6. Booking.com - Multi-Provider Reservation

### Use Case
Aggregate bookings across hotels, flights, car rentals from multiple providers.

### Complexity
- **External APIs**: Third-party provider systems with varying SLAs
- **Atomic bookings**: All-or-nothing for complete itineraries
- **Real-time availability**: Inventory changes during reservation

### Saga Flow
1. Search available hotels, flights, cars
2. Soft-reserve across all providers (hold inventory)
3. Process customer payment
4. Confirm all reservations
5. If any confirmation fails → Cancel all and refund

### Challenges
- **Provider timeouts**: External APIs may be slow or unavailable
- **Partial confirmations**: One provider confirms, another fails
- **Rate limits**: Coordinating many API calls within limits
- **Compensation cost**: Cancellation fees from providers

### Solution Strategy
- Pessimistic soft-locks with expiry (2-10 minutes)
- Parallel confirmation with circuit breakers
- Graceful degradation (show available options if some fail)
- Customer communication about partial failures

---

## 7. Spotify - Account Lifecycle Management

### Use Case
Managing user account changes across services.

### Saga Example: Account Deletion
1. **Identity Service**: Mark account for deletion
2. **Playlist Service**: Anonymize/delete playlists
3. **Social Service**: Remove followers/following
4. **Billing Service**: Cancel subscription, refund if applicable
5. **Storage Service**: Delete user data (GDPR compliance)
6. **Analytics Service**: Anonymize historical data
7. **Identity Service**: Complete deletion

### Key Requirements
- **GDPR compliance**: Must complete within 30 days
- **Data residency**: Different regions have different rules
- **Audit trail**: Prove deletion for regulatory compliance

### Implementation
Long-running saga (days/weeks) with checkpointing and progress tracking.

---

## Common Patterns Across Organizations

### 1. State Persistence
- **Amazon**: DynamoDB
- **Netflix**: Cassandra
- **Uber**: PostgreSQL + Cassandra
- **Microsoft**: Azure Storage

### 2. Messaging Infrastructure
- **Kafka**: Uber, Netflix, LinkedIn
- **RabbitMQ**: Smaller deployments
- **AWS SQS/SNS**: Amazon, cloud-native apps
- **Azure Service Bus**: Microsoft ecosystem

### 3. Orchestration Frameworks
- **Temporal/Cadence**: Uber, HashiCorp, Box
- **Axon Framework**: Java microservices
- **Azure Durable Functions**: Azure customers
- **AWS Step Functions**: AWS customers
- **Custom**: Netflix, Amazon (internal tools)

### 4. Monitoring
- **Distributed Tracing**: Jaeger, Zipkin, AWS X-Ray
- **Metrics**: Prometheus, Datadog, New Relic
- **Logging**: ELK Stack, Splunk, CloudWatch

---

## Success Metrics

### Netflix
- 99.9% saga success rate
- Average compensation time: <5 seconds
- Zero duplicate billings (idempotency working)

### Uber
- Sub-second driver assignment saga
- 99.99% payment processing reliability
- Millions of concurrent active sagas

### Amazon
- Handles Prime Day traffic spikes (10x normal)
- Multi-region saga coordination
- <0.01% compensation rate

---

## Key Takeaways from Industry

1. **Start Simple**: Most companies began with choreography, evolved to orchestration for complex flows
2. **Idempotency is Non-Negotiable**: Every company emphasizes this
3. **Observability First**: Cannot operate sagas without proper monitoring
4. **Gradual Adoption**: Introduced saga for new features, migrated legacy slowly
5. **Team Training**: Requires mindset shift from ACID thinking
6. **Operational Maturity**: Need strong DevOps practices before adopting sagas

---

## When NOT to Use (Industry Lessons)

Companies that tried saga and reverted:
- **Too few services**: Premature microservices adoption
- **Strong consistency required**: Financial ledgers stayed monolithic
- **Team inexperience**: Operational burden too high
- **Over-engineering**: Simple CRUD apps didn't need it

**Rule of thumb**: If you're not Netflix/Uber/Amazon scale, start simpler.
