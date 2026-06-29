# API Gateway Pattern - Diagrams

## 1. Basic Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        CLIENTS                              │
├──────────────┬──────────────┬──────────────┬───────────────┤
│  Mobile App  │   Web App    │  Third-party │  IoT Devices  │
└──────┬───────┴──────┬───────┴──────┬───────┴───────┬───────┘
       │              │              │               │
       └──────────────┴──────────────┴───────────────┘
                              │
                              ▼
       ┌──────────────────────────────────────────────┐
       │         API GATEWAY (Port 8080)              │
       ├──────────────────────────────────────────────┤
       │  • Authentication & Authorization            │
       │  • Rate Limiting & Throttling                │
       │  • Request/Response Transformation           │
       │  • Protocol Translation (REST ↔ gRPC)        │
       │  • Request Aggregation                       │
       │  • Caching                                   │
       │  • Load Balancing                            │
       │  • Circuit Breaker                           │
       │  • Logging & Monitoring                      │
       └──────┬───────┬────────┬─────────┬────────────┘
              │       │        │         │
    ┌─────────┼───────┼────────┼─────────┼─────────┐
    │         │       │        │         │         │
    ▼         ▼       ▼        ▼         ▼         ▼
┌─────┐   ┌─────┐ ┌──────┐ ┌─────┐  ┌────────┐ ┌──────┐
│User │   │Order│ │Product│ │Payment│ │Inventory│ │Analytics│
│Svc  │   │Svc  │ │Svc   │ │Svc   │ │Svc     │ │Svc    │
└─────┘   └─────┘ └──────┘ └─────┘  └────────┘ └──────┘
:3001     :3002    :3003    :3004     :3005      :3006
```

## 2. Request Flow dengan Aggregation

```
Client Request: GET /api/dashboard
         │
         ▼
    ┌─────────┐
    │ Gateway │
    └────┬────┘
         │
         │ Parallel Requests
         ├─────────────┬─────────────┬──────────────┐
         │             │             │              │
         ▼             ▼             ▼              ▼
    ┌────────┐   ┌─────────┐   ┌────────┐    ┌──────────┐
    │  User  │   │  Orders │   │Products│    │Analytics │
    │Service │   │ Service │   │Service │    │ Service  │
    └───┬────┘   └────┬────┘   └───┬────┘    └────┬─────┘
        │             │             │              │
        │ Profile     │ Recent      │ Recommend    │ Stats
        │ Data        │ Orders      │ -ations      │ Data
        │             │             │              │
        └─────────────┴─────────────┴──────────────┘
                          │
                          ▼
                    ┌─────────┐
                    │ Gateway │  Aggregate Response
                    └────┬────┘
                         │
                         ▼
                  {
                    "user": {...},
                    "orders": [...],
                    "recommendations": [...],
                    "stats": {...}
                  }
                         │
                         ▼
                      Client
```

## 3. Authentication Flow

```
1. Login Request
   Client ──────► Gateway ──────► Auth Service
                    │                   │
                    │                   │ Validate
                    │                   │ Credentials
                    │                   │
                    │ ◄────────────── JWT Token
                    │
                    └──────────────► Client (Store Token)

2. Authenticated Request
   Client ──────► Gateway
   (+ JWT Token)    │
                    │ Verify JWT
                    │ Extract User Info
                    │
                    ├──────────────► Backend Service
                    │   (+ X-User-Id header)
                    │
                    │ ◄────────────── Response
                    │
                    └──────────────► Client
```

## 4. Rate Limiting Strategy

```
┌─────────────────────────────────────────────────┐
│              Rate Limiter                       │
│  ┌─────────────────────────────────────────┐   │
│  │  Tier        Requests    Window         │   │
│  │  ────────────────────────────────────   │   │
│  │  Free        100         15 minutes     │   │
│  │  Basic       1,000       15 minutes     │   │
│  │  Premium     10,000      15 minutes     │   │
│  │  Enterprise  100,000     15 minutes     │   │
│  └─────────────────────────────────────────┘   │
└─────────────────────────────────────────────────┘
                     │
                     ▼
   Request with API Key / JWT
                     │
                     ▼
            ┌────────────────┐
            │ Identify User  │
            │ & Check Limit  │
            └────────┬───────┘
                     │
            ┌────────┴────────┐
            │                 │
       ▼ Limit OK        ▼ Limit Exceeded
   Forward Request      HTTP 429
   to Backend          Too Many Requests
                       Retry-After: 900
```

## 5. Circuit Breaker Pattern Integration

```
Gateway Request to Backend Service
            │
            ▼
    ┌───────────────┐
    │Circuit Breaker│
    │   State       │
    └───────┬───────┘
            │
    ┌───────┴───────────────────────────────┐
    │                                       │
    ▼ CLOSED                          ▼ OPEN
(Normal Operation)              (Service Down)
    │                                       │
    │ Request                               │ Return Error
    │ to Service                            │ or Fallback
    │                                       │
    ├─ Success ────► Reset Counter          │
    │                                       │
    ├─ Failure ────► Increment Counter      │
    │                    │                  │
    │                    ▼                  │
    │            Threshold Reached?         │
    │              Yes │      │ No          │
    │                  │      │             │
    │        ┌─────────┘      └─► Continue │
    │        │                              │
    │        ▼                              │
    │   OPEN State ◄───────────────────────┘
    │        │
    │        │ Wait Timeout
    │        ▼
    │   HALF-OPEN
    │        │
    │        │ Test Request
    │        ├─ Success ──► CLOSED
    │        └─ Failure ──► OPEN

States:
• CLOSED: Normal operation, requests pass through
• OPEN: Service unavailable, fail fast
• HALF-OPEN: Testing if service recovered
```

## 6. Caching Layers

```
┌─────────────────────────────────────────────────┐
│                  CLIENT                         │
└───────────────────┬─────────────────────────────┘
                    │
                    ▼
         ┌──────────────────────┐
         │  Browser Cache       │  Cache-Control: max-age=3600
         │  (HTTP Headers)      │
         └──────────┬───────────┘
                    │ Cache Miss
                    ▼
         ┌──────────────────────┐
         │  CDN Cache           │  Edge locations
         │  (CloudFlare/AWS)    │  TTL: 300s
         └──────────┬───────────┘
                    │ Cache Miss
                    ▼
         ┌──────────────────────┐
         │  API Gateway Cache   │  Redis/Memcached
         │  (In-Memory/Redis)   │  TTL: 60-300s
         └──────────┬───────────┘
                    │ Cache Miss
                    ▼
         ┌──────────────────────┐
         │  Backend Service     │  Database query
         │  Cache               │
         └──────────────────────┘

Cache Invalidation:
• Time-based (TTL)
• Event-based (on update/delete)
• Tag-based (related resources)
```

## 7. High Availability Setup

```
                    Internet
                       │
                       ▼
              ┌────────────────┐
              │  Load Balancer │  (AWS ELB / Nginx)
              │  (Health Check)│
              └────────┬───────┘
                       │
         ┌─────────────┼─────────────┐
         │             │             │
         ▼             ▼             ▼
    ┌────────┐    ┌────────┐    ┌────────┐
    │Gateway │    │Gateway │    │Gateway │
    │  Pod 1 │    │  Pod 2 │    │  Pod 3 │
    └────────┘    └────────┘    └────────┘
    AZ-1          AZ-2          AZ-3
         │             │             │
         └─────────────┼─────────────┘
                       │
              ┌────────┴────────┐
              │                 │
              ▼                 ▼
         ┌─────────┐       ┌─────────┐
         │ Redis   │       │ Redis   │
         │ Master  │──────►│ Replica │
         └─────────┘       └─────────┘
              │
              ▼
    ┌──────────────────┐
    │ Service Discovery│  (Consul/Eureka)
    │                  │
    └──────────────────┘
              │
      ┌───────┴────────┐
      │                │
      ▼                ▼
  Backend Services (Multiple Instances)
```

## 8. Request Lifecycle

```
1. Client → Gateway
   ├─ Extract Headers (Auth, API Key, etc.)
   ├─ Generate Request-ID (tracing)
   └─ Log Request

2. Authentication
   ├─ Validate JWT Token
   ├─ Extract User Info
   └─ Add X-User-Id header

3. Rate Limiting
   ├─ Check User Tier
   ├─ Increment Counter
   └─ Allow or Block (429)

4. Cache Check
   ├─ Generate Cache Key
   ├─ Check Redis
   └─ Return if Hit

5. Service Discovery
   ├─ Lookup Service in Registry
   ├─ Select Instance (Load Balancing)
   └─ Get Service URL

6. Circuit Breaker Check
   ├─ Check Circuit State
   └─ Allow or Fail Fast

7. Request Transformation
   ├─ Protocol Translation (REST→gRPC)
   ├─ Add Headers (Tracing, User-ID)
   └─ Forward Request

8. Backend Processing
   └─ Service processes request

9. Response Transformation
   ├─ Protocol Translation (gRPC→REST)
   ├─ Filter Fields (per client type)
   └─ Cache Response

10. Gateway → Client
    ├─ Add CORS Headers
    ├─ Log Response
    └─ Send to Client
```

## 9. Multi-Region Deployment

```
                     Global DNS
                    (Route 53)
                         │
         ┌───────────────┼───────────────┐
         │               │               │
         ▼               ▼               ▼
    ┌─────────┐     ┌─────────┐     ┌─────────┐
    │ Region  │     │ Region  │     │ Region  │
    │  US-East│     │ EU-West │     │ APAC    │
    └────┬────┘     └────┬────┘     └────┬────┘
         │               │               │
         ▼               ▼               ▼
    ┌─────────┐     ┌─────────┐     ┌─────────┐
    │ Gateway │     │ Gateway │     │ Gateway │
    │ Cluster │     │ Cluster │     │ Cluster │
    └────┬────┘     └────┬────┘     └────┬────┘
         │               │               │
         └───────────────┼───────────────┘
                         │
                         ▼
              ┌──────────────────┐
              │ Global Services  │
              │ (Replicated)     │
              └──────────────────┘

Traffic Routing:
• Latency-based routing
• Geo-proximity routing
• Health check failover
```

## 10. API Gateway dengan Backend for Frontend (BFF)

```
┌──────────┐                           ┌──────────┐
│  Mobile  │                           │   Web    │
│   App    │                           │   App    │
└─────┬────┘                           └─────┬────┘
      │                                      │
      │ /mobile/api/*                        │ /web/api/*
      │                                      │
      └────────┬──────────────┬──────────────┘
               │              │
               ▼              ▼
        ┌──────────┐    ┌──────────┐
        │  Mobile  │    │   Web    │
        │   BFF    │    │   BFF    │
        │ Gateway  │    │ Gateway  │
        └─────┬────┘    └─────┬────┘
              │               │
              └───────┬───────┘
                      │
         ┌────────────┼────────────┐
         │            │            │
         ▼            ▼            ▼
    ┌────────┐  ┌─────────┐  ┌────────┐
    │ User   │  │ Product │  │ Order  │
    │Service │  │ Service │  │Service │
    └────────┘  └─────────┘  └────────┘

Benefits:
• Mobile BFF returns optimized payload (smaller)
• Web BFF returns full data
• Each BFF tailored to client needs
```
