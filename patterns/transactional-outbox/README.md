# Transactional Outbox Pattern

## Ringkasan

**Transactional Outbox** adalah sebuah arsitektur design pattern yang digunakan untuk mempublikasikan event atau pesan secara andal (*reliable*) dalam arsitektur distributed system (seperti Microservices). Pattern ini memastikan bahwa perubahan status pada database internal aplikasi dan pengiriman pesan terkait ke message broker (seperti Apache Kafka, RabbitMQ, dll.) terjadi secara atomik—**secara mutlak semuanya berhasil (*commit*) atau semuanya batal (*rollback*)**.

## Problem yang Diselesaikan

Di dalam arsitektur microservices, sebuah service sering kali perlu melakukan dua hal setelah menerima request dari user:
1. **Mengubah state internal database** (misalnya: menyimpan pesanan baru ke tabel `orders`).
2. **Mengirimkan event pemberitahuan ke service lain** (misalnya: mempublikasikan event `OrderCreated` ke message broker agar Payment Service bisa memproses pembayaran).

### Masalah jika tidak memakai Transactional Outbox:
Ada potensi kegagalan sistem (*dual-write problem*) ketika dua operasi tersebut dilakukan secara terpisah:
- **Skenario A (Ubah DB dulu, lalu kirim event)**: Aplikasi berhasil mengubah data di database, namun sebelum event sempat terkirim, aplikasi mengalami *crash* atau jaringan ke message broker terputus. Akibatnya, database konsisten tetapi service lain (konsumen) tidak pernah tahu bahwa ada pesanan baru berjalan (*event lost*).
- **Skenario B (Kirim event dulu, lalu ubah DB)**: Aplikasi sukses mempublikasikan event ke broker, namun saat ingin menyimpan data ke database aplikasi menemui kendala (misal: constraint violation atau DB down) sehingga transaksi database dibatalkan. Akibatnya, payment service akan memotong saldo user untuk pesanan yang sebenarnya tidak pernah terdaftar/terbuat di sistem (*phantom event/ghost data*).

Pattern **Transactional Outbox** menyelesaikan dual-write problem ini lewat jaminan **At-Least-Once Delivery** tanpa memerlukan distributed transactions (2PC - Two-Phase Commit) yang lambat, kompleks, dan berbiety tinggi.

## Cara Kerja Transactional Outbox

1. **Penulisan Atomik Lokal**: Saat melakukan perubahan data bisnis utama, database transaksi lokal juga menulis informasi event tersebut ke tabel khusus bernama `outbox_events` (atau tabel *outbox*) dalam satu transaksi database yang sama (Atomik). Jika transaksi gagal, seluruh perubahan bisnis dan event outbox akan di-rollback.
2. **Proses Message Relay (Pemancar Pesan)**: Komponen terpisah yang disebut dengan *Message Relay* atau *Outbox Publisher* berjalan di latar belakang untuk melakukan polling secara periodik pada tabel `outbox_events` mencari data dengan status `PENDING`, kemudian mempublikasikannya ke Message Broker.
3. **Konfirmasi & Tandai**: Setelah broker mengonfirmasi penerimaan event, Message Relay memperbarui status event tersebut di database lokal menjadi `PROCESSED` atau mendelatenya agar tidak dikirim ulang.

Ada dua metode utama untuk mengimplementasikan Message Relay:
- **Transaction Log Mining (Debezium/CDC - Change Data Capture)**: Membaca commit log database secara langsung. Sangat efisien dan berkinerja tinggi, meminimalkan beban query pada database.
- **Polling Publisher**: Melacak status tabel lewat query database periodik. Sangat sederhana untuk diimplementasikan tetapi memberikan overhead query tambahan ke database utama.

## Implementation Guide (Panduan Implementasi)

Implementasi sederhana dengan Python menggunakan SQLite sebagai database lokal dan penyedia mekanisme transaksi atomik.

### File-file dalam Pattern Ini:
- `outbox.py`: Implementasi business service (`OrderService`) dan komponen pemancar (`MessageRelay`).
- `test_outbox.py`: Unit test untuk memverifikasi fungsionalitas transaksi atomik dan mekanisme ketahanan jaringan.
- `diagram.md`: Diagram alur proses arsitektur Transactional Outbox.

### Contoh Kunci Kode Sumber (`outbox.py`):
```python
# Menulis ke database bisnis dan tabel outbox secara atomik (dalam satu transaksi)
with sqlite3.connect("app.db") as conn:
    conn.execute("BEGIN TRANSACTION")
    try:
        # 1. Simpan pesanan ke database utama
        conn.execute(
            "INSERT INTO orders (id, customer_id, amount, status) VALUES (?, ?, ?, ?)",
            (order_id, customer_id, amount, "CREATED")
        )
        
        # 2. Append event ke tabel outbox_events
        event_id = str(uuid.uuid4())
        payload = json.dumps({"order_id": order_id, "amount": amount})
        conn.execute(
            "INSERT INTO outbox_events (id, aggregate_type, aggregate_id, event_type, payload) VALUES (?, ?, ?, ?, ?)",
            (event_id, "Order", order_id, "OrderCreated", payload)
        )
        
        # Selesai secara atomik
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
```

Untuk memverifikasi cara kerja program secara mandiri, jalankan pengujian berikut di root directory:
```bash
python3 -m unittest discover -s patterns/transactional-outbox/ -p "test_*.py" -v
```

## Trade-offs dan Pertimbangan (Considerations)

### Keuntungan (Advantages)
- **Konsistensi Tertinggi**: Menjamin event dikirimkan minimal satu kali (*at-least-once delivery*) setiap terjadi perubahan data.
- **Performa Tinggi**: No distributed transaction locks. Hanya bertumpu pada transaksi ACID database lokal yang sudah dioptimalkan.
- **Loose Coupling**: Bisnis service tidak terhambat jika Broker Pesan sedang mengalami downtime. Pengiriman event ditunda secara aman di db lokal hingga broker pulih.

### Kerugian (Disadvantages)
- **Potensi Duplikasi Event (Duplicate Messages)**: Jika Message Relay sukses mengirim ke broker namun crash sebelum sempat update status event menjadi `PROCESSED`, event yang sama akan dikirim ulang. Konsekuensinya, **subscriber/konsumen wajib bersifat idempotent**.
- **Latency Pengiriman**: Sedikit jeda pengiriman data karena adanya rentang waktu polling dari Message Relay (jika menggunakan Polling Publisher).
- **Perawatan DB Extra**: Perlu strategi pembersihan data tabel outbox secara berkala (misal menghapus event yang sudah berstatus `PROCESSED` lebih dari 7 hari) agar tabel tidak membengkak.

### When to Use
- Sistem microservices berbasis HTTP yang membutuhkan integrasi event-driven.
- Modifikasi database dan publikasi event yang bersifat krusial untuk konsistensi sistem (misalnya: pembuatan invoice, registrasi akun, checkout belanjaan).
- Perlu jaminan bahwa pesan tidak boleh hilang meskipun ada kegagalan infrastruktur sementara.

### When to Avoid
- Aplikasi monolitik sederhana yang tidak memerlukan komunikasi eksternal.
- Skenario di mana duplikasi data atau kehilangan pesan sesekali tidak berbahaya bagi bisnis.
- Transaksi real-time dengan latensi sangat ketat (sub-millisecond) di mana penulisan disk database ganda menjadi bottleneck.

## Scalability Considerations

1. **Transaction Log Mining (CDC)**: Pada skala traffic tinggi (ratusan ribu transaksi per detik), polling manual menggunakan query database SQL (`SELECT...WHERE status='PENDING'`) akan membuat database kewalahan karena memicu CPU spikes dan table lock. Gunakan tools CDC seperti Debezium yang membaca binary log (WAL/Binlog) tanpa membebani thread query database.
2. **Pembersihan Data (Partition & Prune)**: Data lama yang sudah terkirim harus dibersihkan secara kontinu. Pendekatan terbaik adalah membuat *tabel berbasis partisi bulanan/harian*, sehingga partisi lama yang sudah selesai diproses dapat langsung di-drop dengan cepat tanpa memicu eksklusi tabel yang lama (`DELETE FROM...`).
3. **Idempotensi Penerima (Idempotent Consumer)**: Konsumen harus mendeteksi ID event yang sudah pernah diproses menggunakan teknik idempotensi (seperti menggunakan tabel unik `processed_events` di sisi database konsumen) untuk mencegah pemrosesan ganda akibat mekanisme *at-least-once*.

## Real-World Examples

- **Uber**: Uber menggunakan Transactional Outbox yang dipadukan dengan CDC untuk memicu workflow perjalanan driver. Saat record order selesai dimasukkan ke database, event dilemparkan ke Kafka secara andal untuk menghitung tarif dan asuransi.
- **Debezium + Kafka Connect**: Menjadi standar industri de-facto untuk menerapkan pattern outbox secara out-of-the-box tanpa coding daemon relay manual pada basis DB Postgres, MySQL, dan SQL Server.
- **Stripe**: Menggunakan variasi outbox pattern pada processing engine mereka untuk memastikan status transaksi user terkirim ke platform partner eksternal secara konsisten tanpa kehilangan data.

## Referensi & Further Reading

- [Microservices Patterns - Chris Richardson (Transactional Outbox Pattern)](https://microservices.io/patterns/data/transactional-outbox.html)
- [Designing Data-Intensive Applications - Martin Kleppmann (The Dual-Write Problem)](https://www.oreilly.com/library/view/designing-data-intensive-applications/9781491903063/)
- [Debezium Documentation - Outbox Event Router](https://debezium.io/documentation/reference/stable/transformations/outbox-event-router.html)
- [Microsoft Architecture Guide - Outbox Pattern](https://learn.microsoft.com/en-us/azure/architecture/best-practices/transactional-outbox)
