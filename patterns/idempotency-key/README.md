# Idempotency Key Pattern

## Ringkasan

**Idempotency Key** adalah arsitektur *design pattern* yang menjamin bahwa sebuah operasi (khususnya mutasi data non-idempotent seperti transfer uang, checkout belanja, atau pembuatan resource) hanya akan dieksekusi **tepat satu kali (exactly-once)**, bahkan jika request yang sama terkirim berulang kali akibat kegagalan jaringan atau retry dari sisi client.

Mekanisme ini diimplementasikan dengan meminta client mengirimkan pengidentifikasi unik (biasanya berupa UUID v4) dalam header HTTP (misalnya `Idempotency-Key` atau `X-Idempotency-Key`). Server kemudian melacak status dan menyimpan response hasil request tersebut di dalam distributed cache (seperti Redis) dengan batas waktu tertentu (TTL).

---

## Cara Kerja Idempotency Key

Berikut adalah alur eksekusi saat client mengirimkan request dengan Idempotency Key:

```
 Client               API Gateway / Service              Redis Cache            Database
   |                            |                             |                    |
   |--- 1. POST /payments ----->|                             |                    |
   |    (Idempotency-Key)       |--- 2. Cek status key ------>|                    |
   |                            |    (try_lock)               |                    |
   |                            |                             |                    |
   |                            |<-- 3. LOCK_ACQUIRED --------|                    |
   |                            |    (Status: PROCESSING)     |                    |
   |                            |                             |                    |
   |                            |--- 4. Eksekusi transaksi DB -------------------->|
   |                            |                                                  |
   |                            |<-- 5. Transaksi Sukses --------------------------|
   |                            |                             |                    |
   |                            |--- 6. Simpan hasil response |                    |
   |                            |    & Ubah status -> COMPLETED                    |
   |                            |---------------------------->|                    |
   |                            |                             |                    |
   |<-- 7. Response (200 OK) ---|                             |                    |
   |                            |                             |                    |
   |   (Retry karena RTO dll)   |                             |                    |
   |--- 8. POST /payments ----->|                             |                    |
   |    (Idempotency-Key)       |--- 9. Cek status key ------>|                    |
   |                            |                             |                    |
   |                            |<-- 10. Status: COMPLETED ---|                    |
   |                            |    (Kembalikan Cached Resp) |                    |
   |                            |                             |                    |
   |<-- 11. Response (200 OK) --|                             |                    |
   |    (Hasil dari Cache)      |                             |                    |
```

### Tahapan Proses Detil:
1. **Try Lock (Atomic Check & Write)**: Ketika request masuk dengan Idempotency Key, server secara atomik memeriksa status key di Redis:
   - **Key Tidak Ditemukan**: Server membuat record baru dengan status `PROCESSING` dan mengatur Time-to-Live (TTL, misal 24 jam). Proses bisnis berlanjut ke database.
   - **Status `PROCESSING`**: Berarti request yang sama sedang diproses secara paralel oleh engine lain. Server langsung merespons dengan HTTP Status `409 Conflict` (atau antrian balik) guna mencegah kondisi balapan (*race condition*) / *duplicate execution*.
   - **Status `COMPLETED`**: Berarti request sudah sukses dieksekusi sebelumnya. Server langsung mengambil respons yang telah disimpan di Redis (cache hit) dan mengembalikan respons tersebut kepada client tanpa menyentuh database atau third-party API lagi.
2. **Execute Business Logic**: Setelah lock didapatkan, server menjalankan logika transaksi utama (e.g. potong saldo bank, simpan data).
3. **Commit Response**: Jika berhasil, server menyimpan kode status HTTP dan body response di Redis, lalu mengupdate status key menjadi `COMPLETED`.
4. **Release Lock (Error Fallback)**: Jika logika bisnis gagal atau terjadi error, server menghapus key tersebut dari Redis (atau membebaskan status `PROCESSING`) agar client dapat mencoba lagi (*retry*) dengan payload yang benar.

---

## Masalah yang Diselesaikan

### 1. Duplikasi Transaksi Finansial
Masalah klasik di mana user menekan tombol "Bayar" dua kali karena tombol tidak ter-disable dengan baik atau koneksi internet lambat. Server tanpa proteksi idempotensi akan memotong saldo user sebanyak dua kali.

### 2. Retry Storms di Jaringan Tidak Andal
Di distributed system, kegagalan koneksi di tengah jalan (misal socket timeout setelah database commit tetapi sebelum return HTTP response ke client) memaksa server client (atau service pengirim) melakukan retry otomatis. Tanpa Idempotency Key, retry ini akan memicu duplikasi data di backend penerima.

### 3. Masalah Penulisan Ganda (Dual-Write Execution)
Mencegah eksekusi ganda pada integrasi API third-party (seperti SMS gateway, e-wallet, billing subscription) yang tidak mendukung idempotensi bawaan secara andal di tingkat platform mereka.

---

## File-file dalam Implementasi Ini

Di dalam repository folder ini:
*   `idempotency.py`: Logika inti dari `IdempotencyManager` yang berinteraksi secara atomic menggunakan skrip Lua ke Redis untuk mengelola *locking* dan *caching*.
*   `example_payment.py`: Modul simulasi transaksi perbankan/pembayaran yang menggunakan `IdempotencyManager` untuk mengamankan proses transfer saldo.
*   `test_idempotency.py`: *Suite* pengujian unit (unit testing) komprehensif menggunakan pytest untuk memvalidasi skenario sukses pertama kali, cache hit (replay), kegagalan rollback lock, dan pemblokiran concurrent requests.

---

## Panduan Penggunaan Singkat

Berikut contoh implementasi sederhana di service Anda:

```python
from idempotency import IdempotencyManager
from example_payment import MockDatabase, PaymentService
import redis

# Inisialisasi client Redis dan manager
redis_client = redis.Redis(host='localhost', port=6379, db=0)
idempotency_mgr = IdempotencyManager(redis_client, expiry_seconds=86400) # TTL 24 jam

# Gunakan dalam service layer
db = MockDatabase()
service = PaymentService(idempotency_mgr, db)

# Eksekusi pembayaran pertama (mengembalikan response baru dan mencatatkan key)
response, status = service.process_payment(
    client_id="user-avatar-1", 
    idempotency_key="tx-uniq-uuid-999", 
    from_acc="acc-1", 
    to_acc="acc-2", 
    amount=250.0
)

# Eksekusi pembayaran kedua dengan key yang sama (mengembalikan response dari cache)
response_cached, status_cached = service.process_payment(
    client_id="user-avatar-1",
    idempotency_key="tx-uniq-uuid-999",
    from_acc="acc-1",
    to_acc="acc-2",
    amount=250.0
)
```

---

## Trade-offs dan Pertimbangan

### Kelebihan (Pros)
1. **Keamanan Transaksi Mutlak**: Menjamin integritas finansial dengan meniadakan duplikasi pembayaran tak disengaja.
2. **Kompabilitas Retry yang Aman**: Client dapat dengan berani menerapkan kebijakan *aggressive retry* di sisi network layer mereka.
3. **Mencegah Overload**: Menghemat beban database dan downstream system karena request duplikat langsung di-handle di layer distributed cache terdepan.

### Kekurangan (Cons)
1. **Overhead Tambahan Latensi**: Setiap request menulis ke Redis sebelum berinteraksi dengan database (meskipun latensi Redis sangat kecil, sub-millisecond).
2. **Kompleksitas State**: Memerlukan pembersihan periodik (TTL) dan penanganan edge case jika Redis mati atau cluster terpisah (pembagian partition).
3. **Penyimpanan (Storage Cost)**: Menyimpan HTTP response body dalam Redis untuk jutaan transaksi harian membutuhkan memori (RAM) RAM yang memadai.

### Kapan Harus Menggunakan (When to Use)
*   API pembayaran (*payment processing*), refund, transfer dana.
*   API pembuatan order ecommerce (*checkout order*).
*   Mutasi data kritis non-idempotent lainnya (misal: pengiriman email broadcast, SMS OTP, dll).

### Kapan Harus Dihindari (When to Avoid)
*   Endpoint bertipe Read-Only (GET, HEAD, OPTIONS). Secara default, operasi pencarian informasi bersifat idempotent.
*   Operasi mutasi data idempotent bawaan (misalnya PUT untuk memperbarui seluruh profil, atau DELETE untuk menghapus resource permanen).

---

## Pertimbangan Skalabilitas (Scalability Considerations)

1. **Skrip Lua untuk Operasi Atomik**: Menulis logika pengecekan status dan locking menggunakan Lua script di Redis memastikan tidak ada kegagalan *race conditions* saat dua request paralel dari client yang sama masuk pada milidetik yang sama. Skrip Lua dieksekusi secara atomic dan single-threaded di Redis engine.
2. **Kapasitas Redis & Pengaturan TTL**: Batasi ukuran response body yang disimpan. Cukup simpan response body ringkas yang diperlukan client untuk me-render layout. Selalu atur TTL (misal 1 hari s/d 7 hari tergantung SLA rekonsiliasi bisnis).
3. **Pemisahan Kunci Idempotensi per Client**: Gunakan format key `idempotency:{client_id}:{key}` untuk mencegah tabrakan/manipulasi key antar client yang berbeda (*namespace separation*).

---

## Contoh di Dunia Nyata (Real-world Examples)

*   **Stripe**: Memperkenalkan arsitektur `Idempotency-Key` di API header HTTP mereka dan menjadi referensi industri modern untuk standar ini.
*   **Adyen / Braintree / Xendit**: Gerbang pembayaran (payment gateway) global dan lokal mewajibkan penggunaan header unik ini untuk API pemrosesan kartu kredit dan disbursement uang.
*   **AWS (Amazon Web Services)**: Beberapa service control plane (seperti EC2 `RunInstances` API) menggunakan parameter client token guna memastikan proses pembuatan VM tidak terduplikasi saat retry.

---

## Referensi & Bacaan Lebih Lanjut

*   [Stripe Engineering Blog: Designing Robust API Idempotency](https://stripe.com/blog/idempotency)
*   [IETF Draft: The Idempotency-Key HTTP Header Field](https://tools.ietf.org/html/draft-ietf-httpapi-idempotency-key-header-04)
*   [AWS Builder's Library: Making retries safe with idempotent APIs](https://aws.amazon.com/builders-library/making-retries-safe-with-idempotent-APIs/)
