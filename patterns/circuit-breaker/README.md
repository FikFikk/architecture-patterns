# Circuit Breaker Pattern

## Ringkasan

Circuit Breaker adalah design pattern yang mencegah aplikasi terus-menerus mencoba operasi yang kemungkinan besar akan gagal, melindungi sistem dari cascading failure dan memberikan waktu untuk recovery. Pattern ini terinspirasi dari circuit breaker listrik yang memutus aliran saat terjadi overload.

## Problem yang Diselesaikan

### Tantangan dalam Sistem Distributed

1. **Cascading Failures**: Satu service yang down bisa menyebabkan seluruh sistem kolaps
2. **Resource Exhaustion**: Thread pool habis menunggu timeout dari service yang tidak responsif
3. **Slow Response Time**: User experience buruk karena menunggu operasi yang pasti gagal
4. **Lack of Fallback**: Tidak ada mekanisme graceful degradation saat dependency tidak tersedia

### Skenario Nyata

Bayangkan aplikasi e-commerce yang bergantung pada payment gateway eksternal. Ketika payment gateway mengalami downtime:

- **Tanpa Circuit Breaker**: Setiap checkout request akan menunggu timeout (30 detik), thread pool exhausted, seluruh aplikasi menjadi tidak responsif
- **Dengan Circuit Breaker**: Setelah beberapa kali failure, circuit terbuka dan langsung menolak request tanpa mencoba koneksi, memberikan fallback response cepat

## Cara Kerja Circuit Breaker

### Tiga State Utama

1. **CLOSED (Normal)**: Request diteruskan ke service, mencatat success dan failure
2. **OPEN (Tripped)**: Request langsung ditolak, return fallback response
3. **HALF-OPEN (Testing)**: Izinkan sejumlah kecil request untuk test recovery

**Transisi State:**
- CLOSED → OPEN: Ketika failure rate melebihi threshold
- OPEN → HALF-OPEN: Setelah timeout period
- HALF-OPEN → CLOSED: Ketika test request berhasil
- HALF-OPEN → OPEN: Ketika test request masih gagal

Lihat  untuk visualisasi lengkap.

## Implementation

### File-file dalam Pattern Ini

- : Implementasi lengkap thread-safe circuit breaker
- : Contoh penggunaan dengan decorator
- : Integrasi dengan FastAPI dan payment service
- : Unit tests lengkap
- : Visualisasi state transitions dan architecture

### Quick Start

```python
from circuit_breaker import circuit_breaker, CircuitBreakerError
import requests

@circuit_breaker(failure_threshold=3, timeout=30)
def call_payment_api(amount: float, user_id: str):
    response = requests.post(
        "https://api.payment.com/charge",
        json={"amount": amount, "user_id": user_id},
        timeout=5
    )
    response.raise_for_status()
    return response.json()

# Dengan fallback
def checkout(order_id: str, amount: float):
    try:
        result = call_payment_api(amount, order_id)
        return {"status": "success", "transaction_id": result["id"]}
    except CircuitBreakerError:
        # Circuit open, queue untuk diproses nanti
        queue_payment_for_retry(order_id, amount)
        return {"status": "queued", "message": "Processing..."}
```

### Konfigurasi Parameters

- **failure_threshold**: Jumlah failure sebelum circuit OPEN (default: 5)
- **success_threshold**: Jumlah success di HALF-OPEN sebelum CLOSED (default: 2)
- **timeout**: Detik sebelum mencoba HALF-OPEN (default: 60)
- **expected_exception**: Exception type yang dihitung sebagai failure (default: Exception)

## Trade-offs dan Considerations

### Advantages

1. **Fail Fast**: Response cepat daripada menunggu timeout
2. **Resource Protection**: Mencegah thread/connection pool exhaustion
3. **Cascading Failure Prevention**: Isolasi failure dari satu service
4. **Self-Healing**: Automatic recovery detection
5. **Better User Experience**: Fallback response lebih cepat

### Disadvantages

1. **False Positives**: Transient error bisa trigger circuit open
2. **Configuration Complexity**: Perlu tuning threshold yang tepat
3. **State Management**: Perlu synchronized state di distributed system
4. **Testing Difficulty**: Sulit simulate semua scenarios

### When to Use

✅ **Gunakan Circuit Breaker ketika:**
- Memanggil external service atau API
- Service dependency yang bisa intermittent failure
- Operasi yang memiliki timeout signifikan
- Butuh graceful degradation
- Ingin melindungi resource (thread pool, connections)

❌ **Jangan gunakan untuk:**
- Internal function call yang cepat
- Database queries (gunakan connection pool timeout)
- Operations yang harus dijamin executed (payment critical path)

## Real-World Examples

### 1. Netflix Hystrix

Netflix mengembangkan Hystrix (sekarang maintenance mode, diganti Resilience4j) untuk:
- Melindungi akses ke 100+ microservices
- Mencegah cascading failure saat peak traffic
- **Result**: Reduced latency dari 99th percentile 2s → 250ms saat partial outage

### 2. Amazon AWS

AWS menggunakan circuit breaker di:
- API Gateway throttling
- DynamoDB client SDK
- Lambda function retry logic
- **Pattern**: Exponential backoff + circuit breaker untuk prevent thundering herd

### 3. Uber Ringpop

Uber implement distributed circuit breaker untuk:
- Service mesh communication
- Cross-datacenter request routing
- Automatic region failover
- **Scale**: Handle 1M+ requests/second dengan <1ms overhead

### 4. Shopify

E-commerce platform menggunakan circuit breaker untuk:
- Payment gateway integration (Stripe, PayPal)
- Inventory service calls
- Shipping API integration
- **Benefit**: 99.99% uptime meskipun third-party service outage

## Scalability Considerations

### Distributed Circuit Breaker State

Dalam sistem distributed dengan multiple instances, circuit breaker state perlu di-share:

**Option 1: Centralized State (Redis)**
- Semua instance share state via Redis
- Trade-off: Network latency, single point of failure
- Best for: Moderate scale, strong consistency needs

**Option 2: Local State + Gossip Protocol**
- Each instance maintains local state
- Sync via gossip protocol (Consul, etcd)
- Best for: High scale, eventual consistency OK

**Option 3: Hybrid Approach**
- Local decision making
- Periodic sync for metrics aggregation
- Best for: Balance between latency and consistency

### Integration dengan Patterns Lain

1. **Retry Pattern**: Retry dengan exponential backoff sebelum circuit opens
2. **Timeout Pattern**: Essential foundation untuk detect failures
3. **Bulkhead Pattern**: Isolasi resource per service dependency
4. **Fallback Pattern**: Provide alternative response ketika circuit open
5. **Rate Limiting**: Control load, prevent overwhelming recovered service

## Monitoring dan Metrics

### Key Metrics

1. **Circuit State**: Current state (CLOSED/OPEN/HALF-OPEN)
2. **Failure Rate**: Percentage failures dalam time window
3. **Call Volume**: Total requests melalui circuit breaker
4. **Open Duration**: Berapa lama circuit dalam state OPEN
5. **Recovery Time**: Time from OPEN → CLOSED

### Health Check Endpoint

```python
@app.get("/health/circuit-breaker")
async def circuit_breaker_health():
    metrics = payment_breaker.get_metrics()
    return {
        "service": "payment-gateway",
        "circuit_breaker": metrics,
        "healthy": metrics["state"] != "OPEN"
    }
```

## Testing

Jalankan unit tests:

```bash
pip install -r requirements.txt
pytest test_circuit_breaker.py -v
```

Demo interaktif:

```bash
python example_simple.py
```

## Referensi

### Papers dan Articles

1. **"Release It!" - Michael Nygard** (2007)
   - Original popularization of Circuit Breaker pattern
   - Stability patterns untuk production systems

2. **"Fault Tolerance in a High Volume, Distributed System" - Netflix** (2012)
   - Real-world implementation di Netflix scale
   - Hystrix design decisions

3. **Martin Fowler - "CircuitBreaker"** (2014)
   - Authoritative reference untuk pattern
   - https://martinfowler.com/bliki/CircuitBreaker.html

### Libraries

**Python:**
- : Simple circuit breaker implementation
- : Retry with circuit breaker support
- : Lightweight decorator-based

**Java/JVM:**
- : Modern, lightweight circuit breaker
- : Netflix (maintenance mode, masih widely used)
- : Alibaba flow control library

**Go:**
- : Port dari Java circuit breaker
- : Go port of Netflix Hystrix

**Node.js:**
- : Node circuit breaker
- : Hystrix-inspired circuit breaker

### Related Patterns

- Retry Pattern
- Timeout Pattern
- Bulkhead Pattern
- Fallback Pattern
- Rate Limiting

---

**Dibuat oleh**: Hermes Agent  
**Tanggal**: 18 Juni 2026  
**Kategori**: Resilience Patterns, Distributed Systems, Fault Tolerance
