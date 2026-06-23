# Bulkhead Pattern

> *"Sekat kapal mencegah satu kebocoran menenggelamkan seluruh kapal."*

## Daftar Isi

- [Apa Itu Bulkhead Pattern?](#apa-itu-bulkhead-pattern)
- [Analogi & Latar Belakang](#analogi--latar-belakang)
- [Problem yang Diselesaikan](#problem-yang-diselesaikan)
- [Solusi: Isolasi dengan Bulkhead](#solusi-isolasi-dengan-bulkhead)
- [Jenis-Jenis Bulkhead](#jenis-jenis-bulkhead)
- [Cara Kerja](#cara-kerja)
- [Implementation Guide](#implementation-guide)
- [Integrasi dengan Circuit Breaker](#integrasi-dengan-circuit-breaker)
- [Trade-offs](#trade-offs)
- [Kapan Menggunakan & Menghindari](#kapan-menggunakan--menghindari)
- [Scalability Considerations](#scalability-considerations)
- [Real-World Examples](#real-world-examples)
- [Referensi & Further Reading](#referensi--further-reading)

---

## Apa Itu Bulkhead Pattern?

**Bulkhead Pattern** adalah pola arsitektur yang mengisolasi elemen-elemen sistem ke dalam partition atau "sekat" terpisah, sehingga kegagalan di satu partisi **tidak menyebar** ke partisi lain. Nama ini diambil dari istilah maritim: sekat (bulkhead) pada kapal yang membagi lambung kapal menjadi kompartemen-kompartemen kedap air.

```
┌─────────────────────────────────────────────────────┐
│                 TANPA BULKHEAD                       │
│                                                     │
│  ┌──────────────────────────────────────────────┐   │
│  │          Thread Pool Bersama (50 thread)     │   │
│  │                                              │   │
│  │  [Service A] [Service A] [Service A]  ...   │   │
│  │  [Service B] [Service B] [Service B]  ...   │   │
│  │  [Service C] [Service C] [Service C]  ...   │   │
│  │                                              │   │
│  │  ⚠️ Service A lambat → semua thread penuh   │   │
│  │  ⚠️ Service B & C ikut terdampak!           │   │
│  └──────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│                 DENGAN BULKHEAD                      │
│                                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────┐  │
│  │ Pool A       │  │ Pool B       │  │ Pool C    │  │
│  │ (20 thread)  │  │ (20 thread)  │  │(10 thread)│  │
│  │              │  │              │  │           │  │
│  │ [A][A][A]... │  │ [B][B][B]... │  │[C][C]...  │  │
│  │              │  │              │  │           │  │
│  │ ⚠️ A PENUH  │  │ ✅ B NORMAL  │  │✅ C NORMAL│  │
│  └──────────────┘  └──────────────┘  └───────────┘  │
│       TERISOLASI        TIDAK TERDAMPAK              │
└─────────────────────────────────────────────────────┘
```

---

## Analogi & Latar Belakang

### Asal-usul Nama

Istilah **bulkhead** berasal dari dunia perkapalan. Kapal-kapal modern dibagi menjadi beberapa kompartemen kedap air oleh dinding-dinding disebut "sekat" (bulkhead). Jika lambung kapal tertabrak dan satu kompartemen kebocoran, kompartemen lainnya tetap kering, sehingga kapal tidak langsung tenggelam.

Desainer kapal terkenal — termasuk yang merancang Titanic — menggunakan prinsip ini. Sayangnya, desain Titanic memiliki kelemahan: sekat-sekatnya tidak cukup tinggi, sehingga saat air di satu kompartemen mencapai tepi, mengalir ke kompartemen berikutnya (cascading failure).

**Pelajaran arsitektural:** Bulkhead harus dirancang *benar-benar* terisolasi — tidak cukup hanya diberi batas logis, tapi batas fisik/resource yang nyata.

### Konteks Perangkat Lunak

Dalam sistem terdistribusi modern, **kegagalan adalah norma, bukan pengecualian**. Netflix melaporkan bahwa layanan mereka mengalami ribuan kegagalan komponen setiap hari. Pertanyaannya bukan "apakah akan gagal?" tapi "bagaimana sistem merespons kegagalan?"

---

## Problem yang Diselesaikan

### Cascading Failure (Kegagalan Berantai)

```
Skenario buruk tanpa Bulkhead:

1. E-commerce app memiliki 3 fitur: Checkout, Rekomendasi, Ulasan
2. Ketiganya menggunakan thread pool yang sama (100 thread)
3. Service rekomendasi mulai lambat (menunggu ML model besar)
4. Request ke rekomendasi tidak selesai → thread terus bertambah
5. Thread pool habis (100/100 terpakai)
6. Request checkout tidak bisa diproses → thread tidak tersedia
7. Sistem checkout DOWN meskipun tidak ada masalah di sana!
8. Revenue hilang karena bottleneck di fitur non-kritis
```

### Resource Starvation

Tanpa isolasi, satu komponen yang hungry resource bisa menyebabkan:
- **Thread starvation**: Thread pool exhausted
- **Connection pool exhaustion**: Semua DB connection dipakai satu service
- **Memory pressure**: GC overhead memengaruhi semua service
- **CPU throttling**: Satu proses compute-intensive memblokir yang lain

### Lack of Graceful Degradation

```
Tanpa Bulkhead:                  Dengan Bulkhead:
                                 
User request → TIMEOUT           User request → Checkout ✅
     ↓                                ↓
Menunggu semua service           Rekomendasi: "Fitur sementara
     ↓                           tidak tersedia"
500 Error — nothing works        ↓
                                 Pengalaman terdegradasi tapi
                                 fungsi utama tetap jalan
```

---

## Solusi: Isolasi dengan Bulkhead

Bulkhead Pattern menerapkan isolasi resource di level:

1. **Thread Pool Isolation** — Setiap service/operasi mendapat pool thread sendiri
2. **Connection Pool Isolation** — Setiap downstream dependency mendapat connection pool sendiri
3. **Process/Container Isolation** — Setiap service berjalan dalam proses terpisah
4. **Rate Limiting per Tenant** — Setiap tenant mendapat kuota resource sendiri

---

## Jenis-Jenis Bulkhead

### 1. Thread Pool Bulkhead

Paling umum digunakan. Setiap grup operasi mendapat thread pool terdedikasi.

```
┌─────────────────────────────────────────────────────────────┐
│                      API Gateway                            │
└──────────────┬──────────────────┬───────────────────────────┘
               │                  │
     ┌─────────▼──────┐  ┌────────▼───────┐  ┌──────────────┐
     │ Checkout Pool  │  │ Search Pool    │  │ Review Pool  │
     │   20 threads   │  │  15 threads    │  │  10 threads  │
     │   Queue: 50    │  │  Queue: 30     │  │  Queue: 20   │
     └─────────┬──────┘  └────────┬───────┘  └──────┬───────┘
               │                  │                  │
     ┌─────────▼──────┐  ┌────────▼───────┐  ┌──────▼───────┐
     │ Checkout       │  │ Search         │  │ Review       │
     │ Service        │  │ Service        │  │ Service      │
     └────────────────┘  └────────────────┘  └──────────────┘
```

### 2. Semaphore Bulkhead

Menggunakan semaphore untuk membatasi concurrent calls tanpa thread pool terpisah.

```
┌──────────────────────────────────────────────────────┐
│              Semaphore-Based Bulkhead                │
│                                                      │
│  Checkout  ──── Semaphore(10) ────▶ Payment API      │
│  Search    ──── Semaphore(20) ────▶ Elasticsearch    │
│  Shipping  ──── Semaphore(5)  ────▶ FedEx API        │
│                                                      │
│  Jika concurrent calls melebihi batas:              │
│  → Request langsung ditolak (fail-fast)             │
│  → Tidak ada penumpukan antrian                      │
└──────────────────────────────────────────────────────┘
```

### 3. Connection Pool Bulkhead

Memisahkan connection pool database per layanan atau per kritisitas.

```
┌────────────────────────────────────────────────────────────┐
│                    Database Connection Bulkhead            │
│                                                            │
│  ┌─────────────────────┐     ┌──────────────────────────┐  │
│  │ Critical Pool       │     │ Analytics Pool           │  │
│  │ (Checkout, Auth)    │     │ (Report, Dashboard)      │  │
│  │ Max Conn: 80        │     │ Max Conn: 20             │  │
│  │ Priority: HIGH      │     │ Priority: LOW            │  │
│  └──────────┬──────────┘     └──────────────┬───────────┘  │
│             │                               │              │
│             └───────────────┬───────────────┘              │
│                             │                              │
│                    ┌────────▼────────┐                     │
│                    │   PostgreSQL    │                     │
│                    │   (100 conns)   │                     │
│                    └─────────────────┘                     │
└────────────────────────────────────────────────────────────┘
```

### 4. Tenant/Customer Bulkhead (Multi-tenancy)

Memastikan satu customer besar tidak memengaruhi customer lain.

```
┌────────────────────────────────────────────────────────────┐
│              Multi-Tenant Bulkhead                         │
│                                                            │
│  Enterprise A ── Pool A (50 threads) ── Dedicated DB A    │
│  Enterprise B ── Pool B (30 threads) ── Dedicated DB B    │
│  SME Tier     ── Shared Pool (20)    ── Shared DB Cluster  │
│                                                            │
│  Jika Enterprise A overload:                              │
│  Enterprise B & SME tidak terdampak                       │
└────────────────────────────────────────────────────────────┘
```

---

## Cara Kerja

```
                    Incoming Request
                          │
                          ▼
              ┌──────────────────────┐
              │   Bulkhead Manager   │
              │  (Resource Allocator)│
              └──────────┬───────────┘
                         │
          ┌──────────────┼──────────────┐
          │              │              │
          ▼              ▼              ▼
   ┌────────────┐ ┌────────────┐ ┌────────────┐
   │ Partition  │ │ Partition  │ │ Partition  │
   │     A      │ │     B      │ │     C      │
   │            │ │            │ │            │
   │ Thread: 20 │ │ Thread: 15 │ │ Thread: 10 │
   │ Active: 20 │ │ Active: 5  │ │ Active: 2  │
   │ Queue: 5   │ │ Queue: 0   │ │ Queue: 0   │
   └─────┬──────┘ └─────┬──────┘ └─────┬──────┘
         │              │              │
         ▼              ▼              ▼
   [PENUH - reject] [Proses Normal] [Proses Normal]
```

**Alur keputusan:**
1. Request masuk ke Bulkhead Manager
2. Manager routing ke partisi yang tepat (berdasarkan tipe/prioritas)
3. Jika partisi memiliki kapasitas → proses request
4. Jika partisi penuh:
   - Tambahkan ke antrian (jika queue belum penuh)
   - Atau tolak dengan `BulkheadFullException` (fail-fast)
5. Partisi lain tidak terpengaruh sama sekali

---

## Implementation Guide

### Setup

```bash
# Install dependencies
pip install -r requirements.txt
```

### Penggunaan Dasar

```python
# Jalankan contoh sederhana
python bulkhead.py

# Jalankan contoh e-commerce  
python example_ecommerce.py

# Jalankan tests
pytest test_bulkhead.py -v
```

Lihat file-file implementasi:
- `bulkhead.py` — Core implementation (Thread Pool & Semaphore Bulkhead)
- `example_ecommerce.py` — Studi kasus e-commerce lengkap
- `test_bulkhead.py` — Unit & integration tests

---

## Integrasi dengan Circuit Breaker

Bulkhead dan Circuit Breaker adalah **pasangan sempurna** dalam membangun sistem resilien:

```
                    ┌─────────────────────────────────┐
                    │         Resilience Stack         │
                    │                                  │
Request ──▶ Retry ──▶ Bulkhead ──▶ Circuit Breaker ──▶ Service
                    │     │              │             │
                    │  (Resource    (State Machine)   │
                    │   Isolation)  CLOSED/OPEN/HALF  │
                    │                                  │
                    └─────────────────────────────────┘
```

| Pattern | Fungsi | Dimensi Proteksi |
|---------|--------|------------------|
| **Bulkhead** | Isolasi resource | Concurrent requests / antrean |
| **Circuit Breaker** | Stop calling failure service | Error rate / response time |
| **Retry** | Coba lagi setelah gagal | Transient errors |
| **Timeout** | Batasi waktu tunggu | Latency |

**Aturan urutan:** Request harus melewati Bulkhead *sebelum* Circuit Breaker, sehingga thread tidak "terjebak" menunggu CB terbuka.

---

## Trade-offs

### ✅ Keuntungan

| Keuntungan | Penjelasan |
|-----------|-----------|
| **Fault Isolation** | Kegagalan terlokalisasi, tidak menyebar |
| **Graceful Degradation** | Fungsi non-kritis mati, fungsi kritis tetap jalan |
| **Predictable Performance** | Setiap service mendapat resource yang dijamin |
| **Easier Debugging** | Mudah mengidentifikasi bottleneck per partisi |
| **Multi-tenant Fairness** | Satu tenant tidak bisa monopoli resource |

### ❌ Kerugian

| Kerugian | Penjelasan |
|---------|-----------|
| **Resource Overhead** | Thread pool idle = resource terbuang |
| **Sizing Complexity** | Perlu tuning yang hati-hati untuk setiap pool |
| **Code Complexity** | Boilerplate lebih banyak |
| **Potential Underutilization** | Resource reserved tapi tidak selalu dipakai |
| **Configuration Management** | Banyak parameter yang perlu di-monitor |

### Trade-off Utama: Efisiensi vs. Isolasi

```
High Isolation                                 High Efficiency
      │                                              │
      │  [Bulkhead]         [Shared Pool]            │
      │  - Resource terjamin    - Resource fleksibel │
      │  - Low utilization      - High utilization   │
      │  - Guaranteed perf      - Risk of starvation │
      ▼                                              ▼
```

**Rekomendasi:** Gunakan Bulkhead untuk service **critical path** dan shared pool untuk service non-kritis dengan rate limiting.

---

## Kapan Menggunakan & Menghindari

### ✅ Gunakan Bulkhead Ketika:

1. **Downstream dependencies tidak reliable** — Third-party API, legacy service
2. **Mixed criticality services** — Checkout (kritis) + Rekomendasi (non-kritis) berbagi infrastruktur
3. **Multi-tenant application** — Mencegah "noisy neighbor" problem
4. **High-traffic spikes** — Traffic burst tidak boleh mematikan service lain
5. **SLA-bound services** — Ada SLO ketat yang harus dipenuhi

### ❌ Hindari Bulkhead Ketika:

1. **Sistem sederhana dengan satu service** — Overkill, tambahkan complexity tanpa benefit
2. **Resource sangat terbatas** — Tidak ada cukup thread/memory untuk dibagi-bagi
3. **Semua service sama kritisnya** — Tidak ada alasan untuk diferensiasi
4. **Latency sangat sensitif** — Thread pool switching menambah overhead (kecil tapi ada)
5. **Team belum matang** — Operational complexity tinggi, perlu monitoring yang baik

### Decision Matrix

```
                    Apakah dependencies bisa tidak reliable?
                              │
                    ┌─────────┴──────────┐
                   Ya                   Tidak
                    │                    │
          ┌─────────▼──────────┐   Pertimbangkan
          │ Apakah ada mix      │   timeout + retry
          │ criticality service?│   saja
          └─────────┬──────────┘
               ┌────┴────┐
              Ya         Tidak
               │          │
          [GUNAKAN    [Pertimbangkan
          BULKHEAD]    Circuit Breaker
                       saja]
```

---

## Scalability Considerations

### Horizontal Scaling

```
┌─────────────────────────────────────────────────────────────┐
│               Bulkhead dengan Horizontal Scaling            │
│                                                             │
│  Load Balancer                                              │
│       │                                                     │
│  ┌────┴────┐    ┌─────────────────────────────────────┐    │
│  │Instance │    │   Instance 2                        │    │
│  │   1     │    │                                     │    │
│  │ ┌──┐┌──┐│    │  ┌──┐┌──┐                           │    │
│  │ │A ││B ││    │  │A ││B │  ← Setiap instance         │    │
│  │ │  ││  ││    │  │  ││  │    punya Bulkhead sendiri  │    │
│  │ └──┘└──┘│    │  └──┘└──┘                           │    │
│  └─────────┘    └─────────────────────────────────────┘    │
│                                                             │
│  💡 Total capacity = instances × threads per pool          │
└─────────────────────────────────────────────────────────────┘
```

### Adaptive Bulkhead (Dynamic Sizing)

Sistem advanced dapat menyesuaikan ukuran pool secara dinamis:

```
Normal Load:     Checkout(20) | Search(15) | Review(10)
High Checkout:   Checkout(35) | Search(10) | Review(5)  ← Adaptive
Maintenance:     Checkout(40) | Search(10) | Review(--) ← Review off
```

**Implementasi:** Gunakan metrics (thread utilization, queue depth) + feedback loop untuk auto-scaling pool size.

### Distributed Bulkhead

Di lingkungan Kubernetes/cloud-native:

```yaml
# Kubernetes Resource Limits = Physical Bulkhead
resources:
  requests:
    memory: "256Mi"
    cpu: "250m"
  limits:
    memory: "512Mi"      # Bulkhead: memory tidak bocor ke pod lain
    cpu: "500m"          # Bulkhead: CPU terbatas per pod
```

### Monitoring & Metrics yang Perlu Dipantau

| Metric | Threshold | Action |
|--------|-----------|--------|
| `bulkhead.active_threads` | > 90% capacity | Scale out atau redistribute |
| `bulkhead.queue_depth` | > 50% max queue | Alert, kemungkinkan pool undersized |
| `bulkhead.rejected_calls` | > 1% dari total | Segera investigasi atau resize |
| `bulkhead.wait_time_p99` | > 100ms | Resize pool atau optimize downstream |
| `bulkhead.utilization` | Konsisten < 20% | Pool mungkin terlalu besar, kurangi |

---

## Real-World Examples

### Netflix — Hystrix & Resilience4j

Netflix adalah pelopor Bulkhead implementation dalam dunia microservices.

```
Arsitektur Netflix Recommendation System:

User Request
     │
     ▼
┌────────────────────────────────────────────┐
│           API Gateway (Zuul)               │
└──────┬────────────┬───────────────┬────────┘
       │            │               │
  ┌────▼─────┐  ┌───▼────┐  ┌──────▼─────┐
  │ Playback │  │Account │  │Recommend.  │
  │ Pool:50  │  │Pool:30 │  │Pool:20     │
  └────┬─────┘  └───┬────┘  └──────┬─────┘
       │            │               │
  (Video CDN)  (UserDB)    (ML Service)
  
Kegagalan ML Service → Hanya rekomendasi hilang
Playback & Account tetap jalan 100%
```

Netflix menggunakan **Hystrix** (deprecated, digantikan Resilience4j) yang mengimplementasikan:
- Thread pool per dependency
- Semaphore untuk operasi lightweight
- Fallback mechanism ketika pool penuh

### Amazon AWS — Service Quota & Throttling

AWS mengimplementasikan Bulkhead di level platform untuk setiap customer:

```
AWS Account Limits (per region, per service):
- EC2: Max 32 vCPU (default)  → Bulkhead per customer
- RDS: Max 40 instance         → Bulkhead per customer
- Lambda: 1000 concurrent executions → Bulkhead per account

Ini mencegah satu customer "menghabiskan" kapasitas global AWS.
```

### Alibaba — Sentinel Framework

Alibaba mengembangkan **Sentinel**, framework traffic control yang menggabungkan Bulkhead dengan:
- Flow control (rate limiting)
- Circuit breaking
- System adaptive protection

Digunakan saat Alibaba Double 11 (Singles Day) — hari dengan traffic tertinggi di dunia:
- Peak traffic: **583.000 orders/detik** (2019)
- Bulkhead memastikan payment service tidak tumpah ke catalog service
- Graceful degradation: fitur non-kritis (review, wishlist) dimatikan saat puncak

### Google — Per-Service Resource Quotas (Borg/Kubernetes)

Google Borg (cikal bakal Kubernetes) mengisolasi workload menggunakan:
- **Priority classes** — Critical, Best-effort, Burstable
- **Resource quotas** per namespace (= Bulkhead per tim/service)
- **PodDisruptionBudget** — Menjamin minimum healthy pods

```yaml
# Google-style k8s bulkhead
apiVersion: v1
kind: ResourceQuota
metadata:
  name: checkout-quota        # Bulkhead untuk tim checkout
  namespace: checkout
spec:
  hard:
    requests.cpu: "4"
    requests.memory: 8Gi
    limits.cpu: "8"
    limits.memory: 16Gi
    pods: "20"
```

### Stripe — Payment Processing Isolation

Stripe memisahkan workload dengan karakteristik berbeda:
- **Synchronous path** (API calls) — Dedicated thread pool, latency SLA ketat
- **Async path** (webhooks) — Separate worker pool, bisa retry
- **Batch path** (reporting) — Background pool, scheduled off-peak

Isolasi ini memastikan `POST /charges` (kritik bisnis) tidak terdegradasi oleh burst webhook delivery.

---

## Referensi & Further Reading

### Buku

| Judul | Penulis | Relevansi |
|-------|---------|-----------|
| *Release It! Design and Deploy Production-Ready Software* | Michael T. Nygard | Bab tentang stability patterns, asal-usul Bulkhead dalam software |
| *Building Microservices* | Sam Newman | Implementasi Bulkhead di microservices architecture |
| *Designing Distributed Systems* | Brendan Burns | Patterns untuk container-based systems |
| *Site Reliability Engineering* | Google SRE Team | Production resilience practices |

### Artikel & Dokumentasi

- **Microsoft Azure Architecture Center** — [Bulkhead Pattern](https://docs.microsoft.com/en-us/azure/architecture/patterns/bulkhead)
- **Resilience4j Documentation** — [Bulkhead Implementation](https://resilience4j.readme.io/docs/bulkhead)
- **Netflix Tech Blog** — *"Fault Tolerance in a High Volume, Distributed System"*
- **Martin Fowler** — *"Circuit Breaker"* (berkaitan erat dengan Bulkhead)

### Tools & Libraries

| Tool/Library | Bahasa | Implementasi |
|-------------|--------|-------------|
| **Resilience4j** | Java | Thread pool & Semaphore bulkhead |
| **Hystrix** (deprecated) | Java | Thread pool isolation |
| **Polly** | .NET | Bulkhead policy |
| **aiobreaker** | Python | Async circuit breaker (dapat dikombinasikan) |
| **Sentinel** | Java/Go | Alibaba's comprehensive traffic control |
| **Istio** | Kubernetes | Service mesh dengan connection pool limits |
| **Envoy Proxy** | C++ | Upstream connection limits & pending requests |

### Pattern Terkait

| Pattern | Hubungan |
|---------|----------|
| **Circuit Breaker** | Komplemen: CB stop panggilan ke service gagal, Bulkhead batasi concurrent calls |
| **Retry** | Gunakan bersama: retry untuk transient error, Bulkhead untuk isolation |
| **Rate Limiting** | Bulkhead membatasi concurrency, Rate Limiting membatasi throughput per waktu |
| **Timeout** | Wajib dikombinasikan: tanpa timeout, thread di Bulkhead bisa "stuck" selamanya |
| **Sidecar** | Bulkhead bisa diimplementasikan di sidecar proxy (Envoy/Istio) |
| **Strangler Fig** | Saat migrasi, Bulkhead memastikan legacy dan new system tidak saling mempengaruhi |

---

*Pattern ini adalah bagian dari koleksi **Architecture Patterns** — panduan arsitektur perangkat lunak dalam Bahasa Indonesia.*

*Dibuat: Juni 2026 | Kategori: Resilience Patterns | Tingkat: Menengah-Lanjut*
