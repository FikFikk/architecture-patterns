# Backend for Frontend (BFF) Pattern - Diagrams

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Client Layer                            │
├─────────────┬─────────────┬─────────────┬──────────────────┤
│   Web App   │ Mobile App  │  Smart TV   │  IoT Device      │
│             │             │             │                  │
│ React SPA   │ iOS/Android │  TV OS      │  Embedded Linux  │
└──────┬──────┴──────┬──────┴──────┬──────┴──────┬───────────┘
       │             │             │             │
       │             │             │             │
       ▼             ▼             ▼             ▼
┌─────────────────────────────────────────────────────────────┐
│                      BFF Layer                              │
├─────────────┬─────────────┬─────────────┬──────────────────┤
│  Web BFF    │ Mobile BFF  │   TV BFF    │   IoT BFF        │
│             │             │             │                  │
│ • Auth      │ • Auth      │ • Auth      │ • Auth           │
│ • Aggregate │ • Aggregate │ • Aggregate │ • Aggregate      │
│ • Transform │ • Transform │ • Transform │ • Transform      │
│ • Cache     │ • Cache     │ • Cache     │ • Minimal Cache  │
│ • Full data │ • Minimal   │ • TV format │ • Ultra minimal  │
└──────┬──────┴──────┬──────┴──────┬──────┴──────┬───────────┘
       │             │             │             │
       └─────────────┼─────────────┼─────────────┘
                     │             │
              ┌──────▼─────────────▼──────┐
              │   API Gateway             │
              │   (Optional)              │
              │   • Routing               │
              │   • Rate Limiting         │
              │   • SSL Termination       │
              └──────┬────────────────────┘
                     │
       ┌─────────────┼─────────────┬─────────────┐
       │             │             │             │
       ▼             ▼             ▼             ▼
┌─────────────────────────────────────────────────────────────┐
│                  Backend Services                           │
├─────────────┬─────────────┬─────────────┬──────────────────┤
│   User      │  Product    │   Order     │   Notification   │
│  Service    │  Service    │  Service    │   Service        │
│             │             │             │                  │
│ PostgreSQL  │ PostgreSQL  │ PostgreSQL  │   Redis/Queue    │
└─────────────┴─────────────┴─────────────┴──────────────────┘
```

## Request Flow: Mobile App (Simplified)

```
Mobile App                Mobile BFF              Backend Services
    │                         │                         │
    │  GET /api/dashboard     │                         │
    ├────────────────────────>│                         │
    │                         │                         │
    │                         │  GET /users/123         │
    │                         ├────────────────────────>│
    │                         │                         │
    │                         │  GET /orders?user=123   │
    │                         ├────────────────────────>│
    │                         │                         │
    │                         │  GET /recommendations   │
    │                         ├────────────────────────>│
    │                         │                         │
    │                         │<────────────────────────┤
    │                         │  (Aggregate responses)  │
    │                         │  (Transform to minimal) │
    │                         │  (Thumbnail images)     │
    │                         │  (Cache result)         │
    │   Minimal JSON Response │                         │
    │<────────────────────────┤                         │
    │   {                     │                         │
    │     user: {...},        │                         │
    │     orders: [5 items],  │                         │
    │     recs: [4 items]     │                         │
    │   }                     │                         │
```

## Request Flow: Web App (Full Data)

```
Web App                   Web BFF                 Backend Services
    │                         │                         │
    │  GET /api/dashboard     │                         │
    ├────────────────────────>│                         │
    │                         │                         │
    │                         │  Parallel Requests:     │
    │                         │  - GET /users/123       │
    │                         │  - GET /orders?limit=10 │
    │                         │  - GET /recommendations │
    │                         │  - GET /user/stats      │
    │                         ├────────────────────────>│
    │                         │                         │
    │                         │<────────────────────────┤
    │                         │  (Aggregate responses)  │
    │                         │  (Add full images)      │
    │                         │  (Include all metadata) │
    │                         │  (Cache result)         │
    │   Full JSON Response    │                         │
    │<────────────────────────┤                         │
    │   {                     │                         │
    │     user: {...},        │                         │
    │     orders: [10 items], │                         │
    │     recs: [8 items],    │                         │
    │     stats: {...}        │                         │
    │   }                     │                         │
```

## Data Transformation: Mobile vs Web

```
Backend Service Response:
┌─────────────────────────────────────────────────┐
│ {                                               │
│   "id": "prod-123",                             │
│   "name": "Premium Headphones",                 │
│   "description": "High-quality noise-canceling...",│
│   "price": 299.99,                              │
│   "currency": "USD",                            │
│   "images": [                                   │
│     "https://cdn/images/prod-123-large.jpg",   │
│     "https://cdn/images/prod-123-side.jpg",    │
│     "https://cdn/images/prod-123-detail.jpg"   │
│   ],                                            │
│   "stock": 45,                                  │
│   "category": "electronics",                    │
│   "weight": 250,                                │
│   "dimensions": {...},                          │
│   "manufacturer": {...},                        │
│   "warranty": {...}                             │
│ }                                               │
└─────────────────────────────────────────────────┘
                      │
         ┌────────────┴────────────┐
         ▼                         ▼
┌──────────────────┐      ┌──────────────────┐
│   Mobile BFF     │      │    Web BFF       │
│   Transform      │      │    Transform     │
└────────┬─────────┘      └────────┬─────────┘
         │                         │
         ▼                         ▼
┌──────────────────┐      ┌──────────────────┐
│ Mobile Response: │      │  Web Response:   │
│ {                │      │  {               │
│   id: "123",     │      │   id: "123",     │
│   name: "Prem.." │      │   name: "Premium.│
│   price: 299.99, │      │   description: ".│
│   image: "thumb" │      │   price: 299.99, │
│   stock: "in"    │      │   images: [3],   │
│ }                │      │   stock: 45,     │
│                  │      │   ...full data   │
│ Size: 0.5 KB     │      │ }                │
└──────────────────┘      │ Size: 2.1 KB     │
                          └──────────────────┘
```

## Caching Strategy

```
┌──────────────────────────────────────────────────────────┐
│                    Caching Layers                        │
└──────────────────────────────────────────────────────────┘

┌─────────────┐                           ┌─────────────┐
│  Mobile BFF │                           │   Web BFF   │
└──────┬──────┘                           └──────┬──────┘
       │                                         │
       ▼                                         ▼
┌─────────────┐                           ┌─────────────┐
│ In-Memory   │                           │ In-Memory   │
│ Cache (L1)  │                           │ Cache (L1)  │
│             │                           │             │
│ LRU, 1000   │                           │ LRU, 500    │
│ items       │                           │ items       │
│ TTL: 1 min  │                           │ TTL: 30 sec │
└──────┬──────┘                           └──────┬──────┘
       │                                         │
       └────────────────┬────────────────────────┘
                        ▼
                 ┌─────────────┐
                 │ Redis (L2)  │
                 │             │
                 │ Shared cache│
                 │ All BFFs    │
                 │ TTL: 10 min │
                 └──────┬──────┘
                        │
                        ▼
                 ┌─────────────┐
                 │  Backend    │
                 │  Services   │
                 └─────────────┘
```

## Circuit Breaker States

```
┌─────────────────────────────────────────────────────────────┐
│                   Circuit Breaker Lifecycle                 │
└─────────────────────────────────────────────────────────────┘

            ┌──────────────┐
            │   CLOSED     │  (Normal operation)
            │              │  Requests pass through
            └───────┬──────┘
                    │
                    │ Failure threshold reached
                    │ (e.g., 5 failures)
                    ▼
            ┌──────────────┐
            │     OPEN     │  (Failing)
            │              │  Reject all requests
            └───────┬──────┘  Fast fail
                    │
                    │ Recovery timeout
                    │ (e.g., 60 seconds)
                    ▼
            ┌──────────────┐
            │  HALF-OPEN   │  (Testing)
            │              │  Allow test requests
            └───────┬──────┘
                    │
        ┌───────────┴───────────┐
        │                       │
        ▼                       ▼
   Success                  Failure
        │                       │
        │                       │
        ▼                       ▼
   CLOSED ────────────────> OPEN
```

## Scalability: Independent Scaling

```
┌───────────────────────────────────────────────────────────┐
│              Traffic Pattern Example                      │
└───────────────────────────────────────────────────────────┘

Mobile Traffic (High):          Web Traffic (Medium):
┌─────────────────┐            ┌─────────────────┐
│ Mobile BFF      │            │ Web BFF         │
│                 │            │                 │
│ 5 Instances     │            │ 2 Instances     │
│ High CPU/Memory │            │ Medium CPU      │
│                 │            │                 │
│ [▓][▓][▓][▓][▓] │            │ [▓][▓]          │
└─────────────────┘            └─────────────────┘

TV Traffic (Low):               IoT Traffic (Very Low):
┌─────────────────┐            ┌─────────────────┐
│ TV BFF          │            │ IoT BFF         │
│                 │            │                 │
│ 1 Instance      │            │ 1 Instance      │
│ Low CPU         │            │ Minimal         │
│                 │            │                 │
│ [▓]             │            │ [▓]             │
└─────────────────┘            └─────────────────┘

Each BFF scales independently based on its traffic!
```

## Deployment Architecture

```
┌────────────────────────────────────────────────────────────┐
│                    Kubernetes Cluster                      │
└────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────┐
│                      Ingress / Load Balancer               │
│  web.example.com    mobile-api.example.com                 │
└─────┬──────────────────────┬───────────────────────────────┘
      │                      │
      ▼                      ▼
┌─────────────┐        ┌─────────────┐
│ Web BFF     │        │ Mobile BFF  │
│ Deployment  │        │ Deployment  │
│             │        │             │
│ replicas: 3 │        │ replicas: 5 │
│             │        │             │
│ [Pod][Pod]  │        │ [Pod][Pod]  │
│ [Pod]       │        │ [Pod][Pod]  │
│             │        │ [Pod]       │
│             │        │             │
│ Service:    │        │ Service:    │
│ web-bff:8000│        │ mobile:8001 │
└─────┬───────┘        └─────┬───────┘
      │                      │
      └──────────┬───────────┘
                 │
    ┌────────────┴────────────┐
    │                         │
    ▼                         ▼
┌─────────────┐        ┌─────────────┐
│ User        │        │ Product     │
│ Service     │        │ Service     │
└─────────────┘        └─────────────┘
```

## Monitoring Dashboard

```
┌────────────────────────────────────────────────────────────┐
│               BFF Monitoring Dashboard                     │
└────────────────────────────────────────────────────────────┘

Request Rate per BFF:
┌───────────────────────────────────────────────────────────┐
│ Mobile BFF:  ████████████████████ 2,500 req/s            │
│ Web BFF:     ████████████ 1,200 req/s                    │
│ TV BFF:      ███ 300 req/s                               │
└───────────────────────────────────────────────────────────┘

Cache Hit Rate:
┌───────────────────────────────────────────────────────────┐
│ Mobile BFF:  85% ████████▌                                │
│ Web BFF:     72% ███████▎                                 │
└───────────────────────────────────────────────────────────┘

P99 Latency:
┌───────────────────────────────────────────────────────────┐
│ Mobile BFF:  120ms                                        │
│ Web BFF:     180ms                                        │
└───────────────────────────────────────────────────────────┘

Backend Call Distribution (Mobile BFF):
┌───────────────────────────────────────────────────────────┐
│ User Service:     ████████ 40%                            │
│ Product Service:  ████████████ 35%                        │
│ Order Service:    ████ 25%                                │
└───────────────────────────────────────────────────────────┘
```
