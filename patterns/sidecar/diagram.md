# Sidecar Pattern Diagrams

## 1. Arsitektur Dasar Sidecar Pattern

```
┌────────────────────────────────────────────────────────┐
│                   Kubernetes Pod                       │
│                                                        │
│  ┌──────────────────────┐      ┌──────────────────┐   │
│  │                      │      │                  │   │
│  │  Application         │◄────►│    Sidecar       │   │
│  │  Container           │      │    Container     │   │
│  │                      │      │                  │   │
│  │  - Business Logic    │      │  - Logging       │   │
│  │  - Core Features     │      │  - Monitoring    │   │
│  │  - Port 8080         │      │  - Config Mgmt   │   │
│  │                      │      │  - Port 9090     │   │
│  └──────────────────────┘      └──────────────────┘   │
│           │                             │              │
│           └─────────────┬───────────────┘              │
│                         │                              │
│              Shared Network Namespace                  │
│              Shared Storage Volumes                    │
│              Same Lifecycle                            │
└────────────────────────────────────────────────────────┘
                          │
                          │
                          ▼
              ┌───────────────────────┐
              │  External Services    │
              │  - Log Aggregator     │
              │  - Metrics Backend    │
              │  - Config Server      │
              └───────────────────────┘
```

## 2. Logging Sidecar Flow

```
┌─────────────────┐         ┌──────────────────┐         ┌─────────────────┐
│   Application   │         │  Logging Sidecar │         │  Elasticsearch  │
│                 │         │                  │         │   / Loki        │
│  - Writes logs  │────────►│  - Watches logs  │────────►│                 │
│    to /var/log  │  shared │  - Parses        │  HTTP   │  - Stores logs  │
│                 │  volume │  - Batches       │  POST   │  - Indexes      │
│                 │         │  - Forwards      │         │                 │
└─────────────────┘         └──────────────────┘         └─────────────────┘
        │                            │                            │
        │                            │                            │
        └────────────────────────────┴────────────────────────────┘
                      Shared Volume: /var/log/app
```

### Logging Sidecar Detail

```
Application Container:
  app.log ──┐
  error.log ─┼──► Shared Volume (/var/log/app)
  access.log─┘

                    ↓

Sidecar Container:
  1. Watchdog monitors file changes
  2. Read new log lines
  3. Parse & add metadata:
     - timestamp
     - pod name
     - namespace
     - log level
  4. Batch logs (100 entries)
  5. Forward to Elasticsearch

                    ↓

Elasticsearch:
  - Index: app-logs
  - Searchable, aggregatable
  - Retention policies
```

## 3. Config Watcher Sidecar Flow

```
┌───────────────┐      ┌────────────────────┐      ┌─────────────────┐
│  ConfigMap /  │      │  Config Watcher    │      │   Application   │
│    Secret     │      │     Sidecar        │      │                 │
│               │      │                    │      │                 │
│  Updated by   │─────►│  1. Detects change │─────►│  3. Reloads     │
│  kubectl /    │ mount│  2. Validates      │ HTTP │     config      │
│  GitOps       │      │  3. Triggers reload│ POST │  4. Applies     │
│               │      │                    │      │     changes     │
└───────────────┘      └────────────────────┘      └─────────────────┘
                                │
                                │ (alternative)
                                ▼
                       Send SIGHUP signal
```

### Config Watcher Detail

```
1. Initial State:
   ConfigMap version: v1
   App config hash: abc123

2. ConfigMap Updated:
   kubectl apply -f configmap.yaml
   ConfigMap version: v2

3. Sidecar Detects:
   File /etc/config/app.yaml changed
   New hash: def456

4. Sidecar Validates:
   - Parse YAML/JSON
   - Check syntax
   - Validate schema

5. Trigger Reload:
   Option A: POST http://localhost:8080/reload
   Option B: kill -HUP <app_pid>

6. Application:
   - Receives reload signal
   - Re-reads config
   - Applies new settings
   - No downtime
```

## 4. Service Mesh Sidecar (Envoy/Istio)

```
┌───────────────────────────────────────────────────────────┐
│                    Kubernetes Pod                         │
│                                                           │
│   ┌─────────────┐                    ┌───────────────┐   │
│   │             │    Intercepts      │               │   │
│   │ Application │◄──────────────────►│ Envoy Proxy   │   │
│   │             │    all traffic     │   (Sidecar)   │   │
│   │ Port 8080   │                    │               │   │
│   └─────────────┘                    │ - mTLS        │   │
│                                      │ - Load Balance│   │
│                                      │ - Retry       │   │
│                                      │ - Circuit Brk │   │
│                                      │ - Metrics     │   │
│                                      │ - Tracing     │   │
│                                      └───────────────┘   │
│                                              │           │
└──────────────────────────────────────────────┼───────────┘
                                               │
                     ┌─────────────────────────┴───────────────────┐
                     │                                             │
                     ▼                                             ▼
        ┌─────────────────────┐                      ┌──────────────────┐
        │  Control Plane      │                      │  Other Services  │
        │  (Istiod)           │                      │  (via mesh)      │
        │  - Config           │                      │                  │
        │  - Certificates     │                      │  Each with their │
        │  - Telemetry        │                      │  own Envoy       │
        └─────────────────────┘                      └──────────────────┘
```

### Traffic Flow dengan Service Mesh

```
Request Flow:
  Client
    │
    ▼
  Ingress Gateway (Envoy)
    │
    ▼
  Service A Pod
    ├─► Application A (8080)
    └─► Envoy Sidecar (15001)
         │
         │ 1. Intercepts outbound call
         │ 2. mTLS encryption
         │ 3. Load balancing decision
         │ 4. Retry logic
         │ 5. Circuit breaker check
         │ 6. Metrics collection
         │
         ▼
  Service B Pod
    ├─► Envoy Sidecar (15001)
    │    │
    │    │ 1. mTLS decryption
    │    │ 2. Authorization check
    │    │ 3. Rate limiting
    │    │ 4. Forward to app
    │    │
    │    ▼
    └─► Application B (8080)
```

## 5. Monitoring Sidecar dengan Prometheus

```
┌──────────────────────────────────────────────────┐
│               Application Pod                    │
│                                                  │
│  ┌──────────────┐         ┌──────────────────┐  │
│  │              │         │   Metrics        │  │
│  │ Application  │────────►│   Collector      │  │
│  │              │ /metrics│   Sidecar        │  │
│  │ Port 8080    │         │                  │  │
│  └──────────────┘         │ - Scrapes app    │  │
│                           │ - Aggregates     │  │
│                           │ - Exposes :9090  │  │
│                           └──────────────────┘  │
│                                     │           │
└─────────────────────────────────────┼───────────┘
                                      │
                                      │ HTTP GET /metrics
                                      │
                                      ▼
                          ┌───────────────────┐
                          │   Prometheus      │
                          │   Server          │
                          │                   │
                          │ - Scrapes :9090   │
                          │ - Stores TSDB     │
                          │ - Alerts          │
                          └───────────────────┘
                                      │
                                      ▼
                          ┌───────────────────┐
                          │    Grafana        │
                          │   Dashboard       │
                          └───────────────────┘
```

## 6. Multi-Sidecar Pod Example

```
┌─────────────────────────────────────────────────────────────────┐
│                        Complex Pod                              │
│                                                                 │
│  ┌────────────────┐                                             │
│  │  Application   │                                             │
│  │  Container     │                                             │
│  │                │                                             │
│  │  - Port 8080   │                                             │
│  └────────┬───────┘                                             │
│           │                                                     │
│           │  Shared volumes & network                           │
│           │                                                     │
│    ┌──────┴──────┬──────────────┬──────────────┐               │
│    │             │              │              │               │
│    ▼             ▼              ▼              ▼               │
│  ┌─────────┐  ┌─────────┐  ┌──────────┐  ┌──────────┐        │
│  │ Logging │  │ Metrics │  │  Config  │  │   Envoy  │        │
│  │ Sidecar │  │ Sidecar │  │  Watcher │  │  Proxy   │        │
│  │         │  │         │  │  Sidecar │  │  Sidecar │        │
│  │ Fluentd │  │Prometheus│  │          │  │          │        │
│  └─────────┘  └─────────┘  └──────────┘  └──────────┘        │
│      │             │             │              │              │
└──────┼─────────────┼─────────────┼──────────────┼──────────────┘
       │             │             │              │
       ▼             ▼             ▼              ▼
  Elasticsearch  Prometheus   ConfigMap    Service Mesh
```

## 7. Deployment Evolution

### Before Sidecar Pattern:
```
┌─────────────────────────────────┐
│       Monolithic Container      │
│                                 │
│  - Application Code             │
│  - Logging Library              │
│  - Metrics Library              │
│  - Config Management            │
│  - Service Discovery            │
│  - Load Balancing Logic         │
│  - Circuit Breaker              │
│  - Retry Logic                  │
│  - Security/Auth                │
│                                 │
│  Problems:                      │
│  ✗ Code duplication             │
│  ✗ Tight coupling               │
│  ✗ Hard to update               │
│  ✗ Language-specific            │
└─────────────────────────────────┘
```

### After Sidecar Pattern:
```
┌──────────────────┐  ┌──────────────────┐
│   Application    │  │   Sidecar        │
│   Container      │  │   Container      │
│                  │  │                  │
│ - Business Logic │  │ - Logging        │
│ - Core Features  │  │ - Metrics        │
│   ONLY           │  │ - Config Mgmt    │
│                  │  │ - Service Disc   │
│                  │  │ - Load Balance   │
│                  │  │ - Circuit Brk    │
│                  │  │ - Retry          │
│                  │  │ - Security       │
│                  │  │                  │
│ Benefits:        │  │ Benefits:        │
│ ✓ Focused        │  │ ✓ Reusable       │
│ ✓ Simple         │  │ ✓ Standardized   │
│ ✓ Testable       │  │ ✓ Upgradeable    │
└──────────────────┘  └──────────────────┘
```

## 8. Resource Allocation

```
Pod Resource Distribution:

┌─────────────────────────────────────┐
│         Total Pod Resources         │
│                                     │
│  ┌──────────────┐  ┌─────────────┐ │
│  │ Application  │  │   Sidecar   │ │
│  │              │  │             │ │
│  │ CPU: 1000m   │  │ CPU: 200m   │ │
│  │ Memory: 1Gi  │  │ Memory:256Mi│ │
│  │              │  │             │ │
│  │ 83% Pod      │  │ 17% Pod     │ │
│  └──────────────┘  └─────────────┘ │
│                                     │
│  Total: 1.2 CPU, 1.25Gi Memory     │
└─────────────────────────────────────┘

Scale to 10 replicas:
  Application: 10 CPU, 10Gi
  Sidecars:    2 CPU, 2.5Gi
  Total:       12 CPU, 12.5Gi
  Overhead:    ~17% (must plan capacity)
```

## 9. Network Latency Impact

```
Without Sidecar:
  Client ──────► Service A ──────► Service B
         1ms            1ms
  Total: 2ms

With Sidecar Proxy:
  Client ──► Envoy ──► Service A ──► Envoy ──► Service B
        0.1ms   0.1ms         0.1ms   0.1ms
  Total: 2.4ms (~20% overhead)

Mitigasi:
- Use localhost communication (faster)
- Enable HTTP/2 multiplexing
- Connection pooling
- Tune buffer sizes
```

## 10. Lifecycle Management

```
Pod Lifecycle:

1. Pod Created
   ├─► Init Containers run (if any)
   │   └─► Setup, download configs, etc.
   │
2. Main Containers Start (parallel)
   ├─► Application Container starts
   │   └─► Health checks: liveness & readiness
   │
   └─► Sidecar Container starts
       └─► Health checks: liveness & readiness

3. Running State
   ├─► Application serves traffic
   └─► Sidecar provides services

4. Termination
   ├─► Receive SIGTERM
   ├─► Sidecar: Finish forwarding logs/metrics
   ├─► Application: Drain connections
   └─► Containers stop (grace period: 30s)

PreStop Hook (optional):
  Ensure graceful shutdown
  └─► Sidecar finishes pending operations
```

---

Diagram dibuat dalam ASCII art untuk kompatibilitas maksimal.
Untuk production, gunakan tools seperti:
- draw.io / diagrams.net
- Mermaid
- PlantUML
- Lucidchart
