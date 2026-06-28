# Saga Pattern

## Ringkasan

**Saga Pattern** adalah arsitektur pengolahan transaksi terdistribusi (*distributed transaction design pattern*) yang digunakan untuk mengelola konsistensi data di antara beberapa microservices tanpa menggunakan *Two-Phase Commit (2PC)* atau protokol ACID terdistribusi yang lambat dan rentan *deadlock*. 

Saga memecah satu transaksi bisnis besar menjadi serangkaian transaksi lokal (*local transactions*). Setiap langkah dalam Saga memperbarui database lokal milik microservice terkait dan menerbitkan event atau pesan untuk memicu langkah berikutnya. Jika salah satu langkah transaksi lokal gagal, Saga akan menjalankan serangkaian **Compensating Transactions** (transaksi kompensasi) secara terbalik untuk membatalkan (*rollback*) perubahan yang telah dilakukan oleh langkah-langkah sebelumnya, sehingga menjaga konsistensi akhir (*eventual consistency*) seluruh sistem.

---

## Problem yang Diselesaikan

Dalam arsitektur monolithic tradisional, kita menggunakan transaksi ACID database tersentralisasi untuk menjaga integritas data (misalnya menggunakan `BEGIN TRANSACTION` ... `COMMIT` / `ROLLBACK`). 

Namun pada arsitektur microservices modern:
1. **Database-per-Service Pattern**: Setiap microservice memiliki database sendiri yang terisolasi (misal: Order Service pakai PostgreSQL, Payment Service pakai Redis/Stripe, Inventory Service pakai DynamoDB).
2. **Kegagalan Two-Phase Commit (2PC)**: Menggunakan alur 2PC terdistribusi menyebabkan masalah latency jaringan yang tinggi, penguncian data (*resource locking*) yang lama, dan daya tahan (*availability*) sistem yang sangat rendah (jika 1 node down, seluruh transaksi terblokir).
3. **Partial Failures (Kegagalan Sebagian)**: Langkah ke-1 (Create Order) dan Langkah ke-2 (Process Payment) berhasil, tetapi Langkah ke-3 (Reserve Inventory) gagal karena stok habis. Tanpa mekanisme rollback, data menjadi tidak konsisten (uang user terpotong tapi barang tidak terkirim).

**Saga Pattern** menyelesaikan tantangan ini dengan mengganti rollback ACID otomatis dengan mekanisme kompensasi tingkat aplikasi (*application-level rollback*).

---

## Dua Pendekatan Utama Saga Pattern

### 1. Orchestration-based Saga (Berbasis Orkestrasi)
Sebuah komponen terpusat yang disebut **Orchestrator** mengoordinasikan eksekusi transaksi. Orchestrator memberi tahu setiap service apa yang harus dilakukan, menerima respons, dan memutuskan langkah selanjutnya (termasuk memicu kompensasi jika terjadi error).

- **Kelebihan**: Alur transaksi jelas dan mudah dilacak (*centralized logic*), mencegah pergantungan melingkar (*cyclical dependency*), mudah di-maintain untuk alur bisnis kompleks.
- **Kekurangan**: Berisiko menjadi *single point of failure* atau mengandung logika yang terlalu tebal jika tidak didesain dengan baik.

### 2. Choreography-based Saga (Berbasis Koreografi)
Setiap service mendengarkan event terdistribusi (misal via Apache Kafka atau RabbitMQ) dan secara mandiri memutuskan untuk mengeksekusi transaksi lokal atau memicu event baru tanpa manager terpusat.

- **Kelebihan**: Sangat independen (*decoupled*), cocok untuk alur sederhana dengan sedikit service.
- **Kekurangan**: Sulit dilacak (*hard to track*) saat bisnis bertambah kompleks dan rentan terhadap cyclic dependencies antar event.

*(Implementasi dalam repository ini berfokus pada **Orchestration-based Saga**).*

---

## Implementation Guide (Panduan Implementasi)

Implementasi Saga Pattern dalam repository ini dapat ditemukan pada berkas-berkas berikut:

### File-file dalam Pattern Ini:
- `saga.py`: Implementasi core kelas `SagaOrchestrator`, `SagaInstance`, dan `SagaStep` yang mengelola alur transaksi lokal dan eksekusi kompensasi secara terbalik saat terjadi Exception.
- `example_ecommerce.py`: Simulasi alur kerja e-commerce lengkap (Order -> Payment -> Inventory) beserta pengujian skenario sukses dan skenario rollback/kompensasi.
- `test_saga.py`: Unit test lengkap dengan framework `pytest` untuk menguji berbagai skenario Saga (sukses, rollback, dan penanganan kegagalan kompensasi).
- `diagram.md`: Diagram sekuensial Mermaid yang menyesuaikan alur kerja Orchestration dan perbandingannya dengan Choreography.

### Contoh Kode Singkat:

```python
from saga import SagaOrchestrator

# Defined local action and compensation functions
def create_order(ctx):
    return {"order_id": "ORD-1001"}

def cancel_order(ctx):
    print(f"Cancelling order {ctx['order_id']}")
    return True

def process_payment(ctx):
    raise Exception("Insufficient funds")  # Fails here!

def refund_payment(ctx):
    return True

# Build Orchestrator
orchestrator = SagaOrchestrator()
orchestrator.add_step("create_order", create_order, cancel_order)
orchestrator.add_step("process_payment", process_payment, refund_payment)

# Execute
result = orchestrator.execute({"user_id": "usr-1", "amount": 50000})
print(result.status) # Output: SagaStatus.COMPENSATED
```

---

## Pertimbangan & Trade-offs (Considerations)

### Keuntungan (Advantages)
- **High Availability & Scalability**: Menerapkan eventual consistency tanpa melakukan locking database lintas service.
- **Resilience**: Sistem tetap stabil terhadap partial failure karena setiap langkah kegagalan selalu diimbangi dengan tindakan kompensasi yang terukur.
- **Flexibility**: Memungkinkan transaksi terdistribusi yang melibatkan service internal maupun API pihak ketiga (misal: Payment Gateway).

### Kerugian (Disadvantages)
- **Kompleksitas Desain**: Pengembang harus menulis kode tindakan kompensasi untuk setiap tindakan utama (misAL: `Charge` -> `Refund`, `Reserve` -> `Release`).
- **Penyimpanan State**: Membutuhkan penyimpanan status Saga yang andal agar dapat dilanjutkan jika orchestrator mengalami crash mid-flight.
- **Lack of Isolation (ACID 'I')**: Karena setiap transaksi lokal langsung di-commit ke database sebelum Saga selesai seluruhnya, pengguna lain atau service lain dapat melihat data sementara (*dirty reads*).

### When to Use
- Sistem berarsitektur microservices atau terdistribusi yang membutuhkan transaksi multi-service.
- Proses bisnis berdurasi panjang (*long-running business processes*) yang melibatkan verifikasi manual atau eksternal API.
- Ketika Two-Phase Commit (2PC) terlalu lambat dan menjadi bottleneck performa sistem.

### When to Avoid
- Sistem berarsitektur monolithic dengan satu database terpusat (gunakan transaksi ACID standar).
- Sistem transaksi keuangan yang membutuhkan *Absolute Immediate Consistency* (misal: core ledger bank yang ketat tanpa pemulihan kompensasi).

---

## Scalability Considerations

1. **Persistent Saga Execution State**:
   Dalam implementasi produksi, state transaksi Saga (seperti yang ada di `SagaInstance`) tidak boleh hanya disimpan dalam memori RAM server, melainkan harus disimpan di persistent datastore (seperti Redis cluster, PostgreSQL, atau Amazon DynamoDB) agar terhindar dari data loss saat node restarting.
2. **Idempotency pada Compensating Actions**:
   Setiap tindakan kompensasi HARUS bersifat *idempotent*. Jika jaringan tidak stabil dan orchestrator mencoba memanggil fungsi refund 2 kali, hasil akhirnya harus tetap sama dan tidak melakukan refund ganda kepada pelanggan.
3. **Outbox Pattern Integration**:
   Gunakan **Transactional Outbox Pattern** untuk mempublikasikan pesan event dari orchestrator ke message queue (seperti Apache Kafka / RabbitMQ) guna memastikan integritas penyampaian pesan antar service.

---

## Real-World Examples dari Tech Companies

- **Uber**: Menggunakan Saga pattern di arsitektur backend trip-processing mereka untuk mengordinasikan alur pencarian pengemudi, pemesanan kendaraan, kalkulasi tarif, serta charging kartu kredit secara terdistribusi.
- **Netflix**: Mengintegrasikan Saga orchestrator kustom untuk mengelola pipeline pengolahan media dan provisi akun berlangganan pelanggan di seluruh region cloud mereka.
- **eBay / Amazon**: Menggunakan *Choreography/Orchestration Saga* untuk mengelola alur checkout keranjang belanja, pengalokasian persediaan barang dari multi-vendor, dan logistik pengiriman.

---

## Referensi & Further Reading

- Microservices Patterns by Chris Richardson (Manning Publications) - *Chapter 4: Managing transactions with sagas*.
- [Microservices.io - Saga Pattern](https://microservices.io/patterns/data/saga.html)
- Martin Fowler - *Sagas* in Distributed Systems Architecture.
- Temporal.io / Camunda Workflow Engines (Industri Standard Orchestration Frameworks).
