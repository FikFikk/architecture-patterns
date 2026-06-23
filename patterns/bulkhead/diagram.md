# Diagram Arsitektur — Bulkhead Pattern

## Diagram 1: Masalah Tanpa Bulkhead (Cascading Failure)

```
┌─────────────────────────────────────────────────────────────────────┐
│                      E-COMMERCE SYSTEM (BERMASALAH)                 │
│                                                                     │
│  ┌──────────┐    ┌──────────────────────────────────────────────┐   │
│  │  Client  │───▶│           SHARED Thread Pool (100)           │   │
│  └──────────┘    │                                              │   │
│                  │  [Checkout][Checkout][Checkout]...           │   │
│                  │  [Recommend][Recommend][Recommend]...        │   │
│                  │  [Review][Review][Review]...                 │   │
│                  │  ← semuanya campur dalam 1 pool →           │   │
│                  └──────────────────┬───────────────────────────┘   │
│                                     │                               │
│                              ┌──────▼──────┐                        │
│                              │ Step 1:     │                        │
│                              │ ML Service  │                        │
│                              │ jadi LAMBAT │                        │
│                              └──────┬──────┘                        │
│                                     │                               │
│                              ┌──────▼──────┐                        │
│                              │ Step 2:     │                        │
│                              │ Thread      │                        │
│                              │ menumpuk    │                        │
│                              │ (60 thread  │                        │
│                              │  terpakai   │                        │
│                              │  oleh       │                        │
│                              │  Recommend) │                        │
│                              └──────┬──────┘                        │
│                                     │                               │
│                              ┌──────▼──────┐                        │
│                              │ Step 3:     │                        │
│                              │ 100/100     │                        │
│                              │ thread PENUH│                        │
│                              └──────┬──────┘                        │
│                                     │                               │
│                   ┌─────────────────▼──────────────────┐           │
│                   │ CASCADING FAILURE                   │           │
│                   │                                     │           │
│                   │ ❌ Checkout → TIMEOUT               │           │
│                   │ ❌ Review   → TIMEOUT               │           │
│                   │ ❌ Auth     → TIMEOUT               │           │
│                   │ ❌ Payment  → TIMEOUT               │           │
│                   │                                     │           │
│                   │ Semua service DOWN karena           │           │
│                   │ Recommendation Service lambat       │           │
│                   └─────────────────────────────────────┘           │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Diagram 2: Solusi dengan Bulkhead Pattern

```
┌─────────────────────────────────────────────────────────────────────┐
│                      E-COMMERCE SYSTEM (DENGAN BULKHEAD)            │
│                                                                     │
│  ┌──────────┐                                                        │
│  │  Client  │──────────────────────────────────┐                    │
│  └──────────┘                                  │                    │
│                                                ▼                    │
│                                    ┌──────────────────────┐         │
│                                    │   Bulkhead Manager   │         │
│                                    │   (Request Router)   │         │
│                                    └──────┬───────┬───────┘         │
│                                           │       │                 │
│                    ┌──────────────────────┘       └──────────────┐  │
│                    │                                             │  │
│    ┌───────────────▼──────┐   ┌───────────────────┐  ┌──────────▼─┐│
│    │   CHECKOUT POOL      │   │   SEARCH POOL     │  │REVIEW POOL ││
│    │   Thread: 40         │   │   Thread: 30      │  │Thread: 15  ││
│    │   Queue: 100         │   │   Queue: 50       │  │Queue: 30   ││
│    │   Priority: CRITICAL │   │   Priority: HIGH  │  │Priority:   ││
│    │                      │   │                   │  │NORMAL      ││
│    │   Active: 20         │   │   Active: 30/30   │  │Active: 5   ││
│    │   Queue: 5           │   │   Queue: 15/50    │  │Queue: 0    ││
│    │   Status: ✅ OK      │   │   Status: ⚠️ BUSY │  │Status: ✅  ││
│    └──────────┬───────────┘   └─────────┬─────────┘  └──────┬─────┘│
│               │                         │                   │      │
│               ▼                         ▼                   ▼      │
│    ┌──────────────────┐      ┌──────────────────┐  ┌──────────────┐│
│    │ Checkout Service │      │ Search Service   │  │Review Service││
│    │ ✅ JALAN NORMAL  │      │ ⚠️ SEDANG SIBUK  │  │✅ JALAN      ││
│    │                  │      │ (tapi TERISOLASI)│  │  NORMAL      ││
│    │ - Order placed   │      │ - Queue penuh    │  │              ││
│    │ - Payment OK     │      │ - Reject excess  │  │              ││
│    └──────────────────┘      └──────────────────┘  └──────────────┘│
│                                                                     │
│   ✅ Search Sibuk → HANYA Search yang Terdampak                     │
│   ✅ Checkout & Review TIDAK TERPENGARUH sama sekali                │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Diagram 3: Semaphore Bulkhead

```
┌─────────────────────────────────────────────────────────────────────┐
│                    SEMAPHORE BULKHEAD PATTERN                       │
│                                                                     │
│                     Incoming Requests                               │
│                           │                                         │
│              ┌────────────▼────────────────┐                       │
│              │         Handler              │                       │
│              │   (Single Thread Pool)       │                       │
│              └────────────┬────────────────┘                       │
│                           │ dispatch concurrent calls              │
│                           │                                         │
│          ┌────────────────┼────────────────┐                       │
│          │                │                │                        │
│  ┌───────▼───────┐ ┌──────▼───────┐ ┌─────▼────────┐              │
│  │  Semaphore A  │ │ Semaphore B  │ │ Semaphore C  │              │
│  │  max_permits=5│ │ max_permits=3│ │ max_permits=2│              │
│  │               │ │              │ │              │              │
│  │  ████░░  4/5 │ │  ███  3/3   │ │  █░   1/2   │              │
│  │               │ │              │ │              │              │
│  │  1 slot free  │ │  PENUH!      │ │  1 slot free │              │
│  └───────┬───────┘ └──────┬───────┘ └─────┬────────┘              │
│          │                │               │                        │
│          ▼                ▼               ▼                        │
│    ┌─────────┐    ┌───────────────┐ ┌──────────┐                  │
│    │Service A│    │BulkheadFull   │ │Service C │                  │
│    │  ✅ OK  │    │Exception! ❌  │ │  ✅ OK   │                  │
│    └─────────┘    │Request ditolak│ └──────────┘                  │
│                   │  (fail-fast)  │                                │
│                   └───────────────┘                                │
│                                                                     │
│  ⚡ Keuntungan Semaphore: Lebih ringan dari Thread Pool              │
│  (tidak perlu context switch antar thread)                          │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Diagram 4: Integrasi Bulkhead + Circuit Breaker + Retry

```
┌─────────────────────────────────────────────────────────────────────┐
│                    RESILIENCE STACK LENGKAP                         │
│                                                                     │
│                        Request Masuk                                │
│                              │                                      │
│                              ▼                                      │
│              ┌───────────────────────────────┐                      │
│              │      TIMEOUT WRAPPER          │                      │
│              │   (max 3 detik per request)   │                      │
│              └───────────────┬───────────────┘                      │
│                              │                                      │
│                              ▼                                      │
│              ┌───────────────────────────────┐                      │
│              │      RETRY POLICY             │                      │
│              │   (max 3x, exponential backoff│                      │
│              │    hanya untuk 5xx/network)   │                      │
│              └───────────────┬───────────────┘                      │
│                              │                                      │
│                              ▼                                      │
│              ┌───────────────────────────────┐                      │
│              │      BULKHEAD                 │                      │◀ Layer 3
│              │   (isolasi concurrent calls)  │                      │
│              │   Max: 20 threads, Queue: 50  │                      │
│              │   Reject jika penuh (fast!)   │                      │
│              └───────────────┬───────────────┘                      │
│                              │ (hanya jika dapat slot)              │
│                              ▼                                      │
│              ┌───────────────────────────────┐                      │
│              │      CIRCUIT BREAKER          │                      │◀ Layer 4
│              │   CLOSED ──▶ OPEN ──▶ HALF    │                      │
│              │   (stop panggil jika >50% err)│                      │
│              └───────────────┬───────────────┘                      │
│                              │ (hanya jika CB CLOSED)               │
│                              ▼                                      │
│              ┌───────────────────────────────┐                      │
│              │      DOWNSTREAM SERVICE       │                      │
│              │   (External API / Database)   │                      │
│              └───────────────────────────────┘                      │
│                                                                     │
│  Failure Scenario:                                                  │
│  ─────────────────────────────────────────────────────────────────  │
│  Downstream 100% gagal:                                             │
│    → Semua request ke downstream gagal                              │
│    → CB: deteksi errorRate > 50% → buka (OPEN)                     │
│    → Bulkhead: thread tidak stuck, langsung fail-fast dari CB       │
│    → Retry: tidak retry kalau CB OPEN (hemat resource)             │
│    → Timeout: tidak terpacu karena request sudah gagal cepat       │
│    → User: dapat error message cepat, bukan hang                   │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Diagram 5: Multi-Tenant Bulkhead

```
┌─────────────────────────────────────────────────────────────────────┐
│                    MULTI-TENANT SAAS BULKHEAD                       │
│                                                                     │
│                   Incoming API Requests                             │
│                           │                                         │
│                    ┌──────▼──────┐                                  │
│                    │  Auth Layer │ → Identifikasi Tenant            │
│                    └──────┬──────┘                                  │
│                           │                                         │
│                    ┌──────▼──────┐                                  │
│                    │   Router    │                                   │
│                    └──────┬──────┘                                  │
│                           │                                         │
│         ┌────────────┬────┴─────┬──────────────┐                   │
│         │            │          │              │                    │
│ ┌───────▼──────┐ ┌───▼──────┐ ┌▼────────┐ ┌───▼──────────┐        │
│ │ Enterprise A │ │Enterpr. B│ │SME Tier │ │ Free Tier    │        │
│ │ Plan: Gold   │ │Plan:Gold │ │Plan:Std │ │ Plan: Free   │        │
│ │              │ │          │ │         │ │              │        │
│ │ Threads: 50  │ │Thread:50 │ │Thread:20│ │ Threads: 5   │        │
│ │ Queue: 200   │ │Queue:200 │ │Queue:50 │ │ Queue: 10    │        │
│ │ Dedicated DB │ │Ded. DB   │ │Shared DB│ │ Shared DB    │        │
│ │ Priority: 1  │ │Priority:1│ │Prio.: 2 │ │ Priority: 3  │        │
│ └───────┬──────┘ └───┬──────┘ └──┬──────┘ └───┬──────────┘        │
│         │            │           │             │                   │
│     [DB_A]       [DB_B]      [DB_SHARED]   [DB_SHARED]            │
│                                                                     │
│  Skenario: Enterprise A melakukan batch job besar                   │
│  ─────────────────────────────────────────────────────────────────  │
│  ✅ Enterprise A: thread penuh (50/50) — tapi terisolasi            │
│  ✅ Enterprise B: tidak terdampak (pool terpisah)                   │
│  ✅ SME Tier: tidak terdampak (pool terpisah)                       │
│  ✅ Free Tier: tidak terdampak (pool terpisah)                      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Diagram 6: State Machine Bulkhead

```
                      ┌─────────────────────────────┐
                      │     BULKHEAD STATE MACHINE  │
                      └─────────────────────────────┘

    Request masuk
         │
         ▼
    ┌────────┐     pool.active < max_threads?
    │ CHECK  │─────────────────────────────────────YES──▶ Proses request ✅
    │ POOL   │
    └────┬───┘
    (NO - Pool penuh)
         │
         ▼
    ┌────────┐     queue.size < max_queue?
    │ CHECK  │─────────────────────────────────────YES──▶ Tambahkan ke Queue ⏳
    │ QUEUE  │                                               │
    └────┬───┘                                              │
    (NO - Queue penuh)                               (tunggu slot tersedia)
         │                                                  │
         ▼                                                  ▼
    ┌────────────────────────────┐              ┌──────────────────────┐
    │  BulkheadFullException     │              │  Thread tersedia?    │
    │                            │              │                      │
    │  - Log warning             │         YES──┤  Ambil dari queue   │
    │  - Return 503              │         NO───┤  Tunggu (polling)   │
    │  - Increment reject metric │              │  atau timeout?       │
    └────────────────────────────┘              └──────────┬───────────┘
                                                           │
                                                    TIMEOUT?
                                                      │   │
                                                     YES  NO
                                                      │   │
                                              ┌───────┘   ▼
                                              │    Proses request ✅
                                              ▼
                                     TimeoutException ⏰
```

---

## Diagram 7: Kubernetes-Native Bulkhead

```
┌─────────────────────────────────────────────────────────────────────┐
│                  BULKHEAD DI KUBERNETES                             │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                    Kubernetes Cluster                        │   │
│  │                                                             │   │
│  │  Namespace: checkout (ResourceQuota)                        │   │
│  │  ┌──────────────────────────────────────────────────────┐   │   │
│  │  │  CPU quota: 8 cores  │  Memory quota: 16Gi           │   │   │
│  │  │  Max pods: 20        │  Priority: system-critical    │   │   │
│  │  │                                                      │   │   │
│  │  │  [Pod] [Pod] [Pod] [Pod] [Pod]  ← HPA auto-scale    │   │   │
│  │  └──────────────────────────────────────────────────────┘   │   │
│  │                                                             │   │
│  │  Namespace: recommendations (ResourceQuota)                 │   │
│  │  ┌──────────────────────────────────────────────────────┐   │   │
│  │  │  CPU quota: 4 cores  │  Memory quota: 8Gi            │   │   │
│  │  │  Max pods: 10        │  Priority: cluster-medium     │   │   │
│  │  │                                                      │   │   │
│  │  │  [Pod] [Pod] [Pod]  ← Terbatas oleh ResourceQuota  │   │   │
│  │  └──────────────────────────────────────────────────────┘   │   │
│  │                                                             │   │
│  │  Namespace: analytics (ResourceQuota - LOW priority)        │   │
│  │  ┌──────────────────────────────────────────────────────┐   │   │
│  │  │  CPU quota: 2 cores  │  Memory quota: 4Gi            │   │   │
│  │  │  Max pods: 5         │  Priority: cluster-low        │   │   │
│  │  │                                                      │   │   │
│  │  │  [Pod] [Pod]  ← Bisa di-preempt jika cluster penuh  │   │   │
│  │  └──────────────────────────────────────────────────────┘   │   │
│  │                                                             │   │
│  │  Istio Sidecar (DestinationRule) — Connection Pool Limit    │   │
│  │  ┌──────────────────────────────────────────────────────┐   │   │
│  │  │  recommendations:                                    │   │   │
│  │  │    connectionPool:                                   │   │   │
│  │  │      tcp.maxConnections: 100    ← Bulkhead level TCP │   │   │
│  │  │      http.http1MaxPendingReqs: 50 ← Queue limit     │   │   │
│  │  │      http.maxRequestsPerConn: 10  ← Per-conn limit  │   │   │
│  │  └──────────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```
