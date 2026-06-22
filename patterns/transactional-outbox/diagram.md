# Transactional Outbox Pattern Diagram

## Arsitektur Aliran Data (Data Flow Architecture)

```
+---------------------------------------------------------------------------------+
|                                 ORDER SERVICE                                   |
|                                                                                 |
| 1. Request                                                                     |
|    Create Order ----> [ Transaksi Database Lokal ]                              |
|                       |                                                         |
|                       +--> Simpan ke tabel 'orders'                             |
|                       |    (Status: CREATED)                                    |
|                       |                                                         |
|                       +--> Simpan ke tabel 'outbox_events'                      |
|                            (Status: PENDING)                                    |
+--------------------------------------------+------------------------------------+
                                             | Commit Transaction (Atomik)
                                             v
                               +-----------------------------+
                               |     Database Aplikasi       |
                               |  +-----------------------+  |
                               |  | tabel: orders         |  |
                               |  +-----------------------+  |
                               |  | tabel: outbox_events  |  |
                               |  +-----------------------+  |
                               +--------------+--------------+
                                              |
                                              | 2. Polling (Periodik) / Log tailing
                                              v
+---------------------------------------------+------------------------------------+
|                               MESSAGE RELAY DEAMON                              |
|                                                                                 |
|  * Membaca event berturut-turut yang berstatus 'PENDING'                        |
|  * Mengirimkan event tersebut ke Broker Pesan (Message Broker)                 |
+---------------------------------------------+------------------------------------+
                                              |
                                              | 3. Publish Event
                                              v
                              +---------------+---------------+
                              |    MESSAGE BROKER (KAFKA)     |
                              |  +-------------------------+  |
                              |  | Topic: order-events      |  |
                              |  +----------+--------------+  |
                              +-------------|-----------------+
                                            |
                                            | 5. Konsumsi Event
                                            v
                              +-------------+-----------------+
                              |       PAYMENT SERVICE         |
                              |  (Dan service konsumen lain)  |
                              +-------------------------------+

Setelah publish sukses (Step 3), Message Relay menandai status event di database:
* UPDATE outbox_events SET status = 'PROCESSED' (Step 4 - Update db lokal)
```

## State Transition of Outbox Event

```
    [ Event Dibuat ]
           |
           v
    +--------------+
    |   PENDING    |  <------+ (Mengalami kegagalan jaringan saat mengirim)
    +------+-------+         |
           |                 |
     (Polled & Send) --------+
           |
           | (Pengiriman Sukses)
           v
    +--------------+
    |  PROCESSED   |
    +--------------+
```
