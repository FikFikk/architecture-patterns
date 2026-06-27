# Rate Limiting Pattern

## Ringkasan

**Rate Limiting** adalah design pattern arsitektur sistem yang digunakan untuk membatasi jumlah request HTTP atau pemanggilan API yang dapat dilakukan oleh klien (user, IP address, atau API Key) dalam rentang waktu tertentu. Pattern ini sangat krusial untuk menjaga ketersediaan (*availability*), keandalan (*reliability*), dan keamanan (*security*) layanan backend dari lonjakan lalu lintas (traffic spikes), serangan Distributed Denial of Service (DDoS), serta perebutan sumber daya (*noisy neighbor problem*).

## Problem yang Diselesaikan

Dalam sistem terdistribusi modern dan microservices, backend API terbuka terhadap berbagai ancaman eksternal dan internal:
1. **DDoS & Service Overload**: Lonjakan request mendadak dapat membuat database down atau kehabisan thread pool server (cascading failure).
2. **Brute Force & Credential Stuffing**: Penyerang melakukan ribuan request per detik untuk menebak password atau token autentikasi.
3. **Resource Starvation (Noisy Neighbor)**: Satu pengguna yang melakukan scraping atau polling berlebihan dapat memonopoli CPU/RAM server, melambatkan akses bagi pengguna lain.
4. **Uncontrolled Cloud Costs**: Pada penyedia cloud berbasis pay-per-use, traffic liar yang tidak dibatasi menciptakan lonjakan tagihan infrastruktur secara eksponensial.

Pattern **Rate Limiting** menyelesaikan masalah ini dengan mekanisme pencegahan dini di layer API Gateway atau Middleware, langsung menolak request berlebih dengan status `HTTP 429 Too Many Requests`.

## Algoritma Utama Rate Limiting

1. **Token Bucket**:
   - Memiliki kapasitas token maksimum. Token diisi ulang secara konstan (*refill rate*). Setiap request mengonsumsi 1 token.
   - **Kelebihan**: Berkompromi sangat baik dengan *burst traffic* (lonjakan singkat).
2. **Leaky Bucket**:
   - Request masuk ke dalam FIFO queue (ember) dan diproses dengan kecepatan konstan (bocor secara konstan).
   - **Kelebihan**: Menghasilkan arus *traffic* output yang sangat stabil dan mulus ke downstream service.
3. **Fixed Window Counter**:
   - Mengurutkan window waktu berdasarkan jam/menit fixed (misal 01:00-01:01).
   - **Kekurangan**: Rentan terhadap spike 2x lipat pada batas perpindahan window waktu.
4. **Sliding Window Counter**:
   - Mengombinasikan counter window sebelumnya dan window saat ini secara terbobot (weighted estimate).
   - **Kelebihan**: Memperbaiki masalah boundary spike dengan kalkulasi statistik memori yang sangat efisien.

## Implementation Guide (Panduan Implementasi)

Implementasi rate limiter dalam repository ini mencakup dua algoritma utama (`TokenBucket` dan `SlidingWindowCounter`) serta `RateLimiterManager` berbasis Python.

### File-file dalam Pattern Ini:
- `rate_limiter.py`: Kelas logika core algoritma Token Bucket, Sliding Window Counter, dan isolated multi-tenant manager.
- `test_rate_limiter.py`: Unit test lengkap untuk menguji perilaku burst, refill rate, window reset, dan isolasi antar klien.
- `diagram.md`: Diagram alur sekuensial interaksi client, gateway, rate limiter, dan microservice backend.

### Contoh Kode Singkat:

```python
from rate_limiter import RateLimiterManager

# Inisialisasi manager (kapasitas 10 request, refill 2 token/detik)
limiter_manager = RateLimiterManager(default_capacity=10, default_refill_rate=2.0)

client_ip = "192.168.1.50"
allowed, meta = limiter_manager.process_request(client_ip)

if allowed:
    print(f"Request diterima. Sisa quota: {meta['remaining_tokens']}")
else:
    print(f"HTTP 429: Too Many Requests. Coba lagi dalam {meta['retry_after_seconds']} detik.")
```

---

## Pertimbangan & Trade-offs (Considerations)

### Keuntungan (Advantages)
- **Perlindungan Infrastruktur**: Mencegah server crash akibat lonjakan traffic tak terduga.
- **Fair Resource Allocation**: Memastikan setiap tenant atau pengguna mendapat jatah jangkauan bandwidth/kuota API yang adil.
- **Penghematan Biaya**: Menghindari pemrosesan request sia-sia yang memicu autoscaling tak terkendali.

### Kerugian (Disadvantages)
- **Kompleksitas Infrastruktur**: Membutuhkan in-memory datastore terdistribusi yang cepat (seperti Redis) untuk mengoordinasikan rate limit antar instance horizontal cluster.
- **Latency Additional**: Setiap request HTTP memerlukan check ke rate limiter store sebelum diproses oleh downstream server (sekitar 1-5ms pertambahan latency).

### When to Use
- Mengspos public REST/GraphQL API ke pihak ketiga (misal: payment gateway, AI API).
- Melindungi endpoint sistem authentication (Login, Register, Reset Password) dari brute force.
- Mengontrol penggunaan resource pada layanan berbiaya tinggi (misal: text generation AI / ML inference).

### When to Avoid
- Komunikasi internal antar microservices yang aman (mTLS internal) dan berada dalam jaringan privat yang sama (lebih disarankan memakai *Bulkhead* atau *Circuit Breaker*).
- System berlatensi ekstrem (high-frequency trading) di mana setiap pertambahan mikrodetik latency tidak dapat ditoleransi.

---

## Scalability Considerations

1. **Distributed Rate Limiting dengan Redis**:
   Pada skala terdistribusi (multi-node Kubernetes cluster), state rate limit harus disimpan di Redis tersentralisasi menggunakan script Lua (`EVAL`) untuk menjamin sifat *atomic execution* tanpa race condition.
2. **Race-Condition & Atomic Operations**:
   Jangan gunakan pola traditional `GET -> Compute in App -> SET`. Gunakan Redis Command seperti `INCRBY` dan `EXPIRE` atau Lua script untuk menjamin konsistensi counter.
3. **HTTP Standard Headers**:
   Sangat disarankan untuk selalu mengembalikan standar HTTP Response Headers untuk transparansi klien:
   - `X-RateLimit-Limit`: Jumlah maksimum request dalam jendela waktu.
   - `X-RateLimit-Remaining`: Sisa kuota request yang tersisa.
   - `X-RateLimit-Reset`: Waktu Unix epoch saat kuota di-reset.
   - `Retry-After`: Jeda detik yang harus ditunggu klien saat terkena HTTP status 429.

---

## Real-World Examples

- **Stripe**: Menggunakan kombinasi Token Bucket & Leaky Bucket di layer Edge API Gateway untuk melindungi financial API mereka dan memberikan error `HTTP 429`.
- **Twitter / X API**: Menerapkan rate limit berbasis OAuth Access Token dan IP address dengan kurun waktu per 15-menit windows.
- **GitHub REST API**: Membatasi 5,000 request per jam untuk authenticated requests dan 60 request per jam untuk unauthenticated requests.
- **Cloudflare**: Menyediakan Web Application Firewall (WAF) dengan fitur Rate Limiting kustom berbasis atribut header, cookie, dan IP address di skala jaringan edge global.

---

## Referensi dan Further Reading

- Martin Fowler — *Patterns of Enterprise Application Architecture*
- Alex Xu — *System Design Interview – An Insider's Guide (Chapter: Design a Rate Limiter)*
- Stripe Engineering Blog: *How we built rate limiting capabilities in our API*
- IETF Internet-Draft: *RateLimit Header Fields for HTTP* (draft-ietf-httpapi-ratelimit-headers)
