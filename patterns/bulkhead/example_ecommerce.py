"""
Bulkhead Pattern — Studi Kasus E-Commerce
==========================================
Simulasi sistem e-commerce yang menggunakan Bulkhead Pattern untuk mengisolasi
berbagai service (Checkout, Rekomendasi, Ulasan, Inventaris) sehingga
overload di satu service tidak memengaruhi yang lain.

Skenario:
- Flash sale tiba-tiba → Checkout traffic spike
- ML Recommendation service lambat → Harus terisolasi dari Checkout
- Review service sedang batch processing → Tidak boleh ganggu yang lain

Penggunaan:
    python example_ecommerce.py
"""

import threading
import time
import random
import logging
from dataclasses import dataclass
from typing import Optional
from bulkhead import (
    ThreadPoolBulkhead,
    SemaphoreBulkhead,
    BulkheadRegistry,
    BulkheadFullException,
    BulkheadMetrics,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)8s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("ecommerce")

# ─────────────────────────────────────────────
# Konfigurasi Bulkhead (disesuaikan SLA)
# ─────────────────────────────────────────────

BULKHEAD_CONFIG = {
    # Service kritis bisnis — thread banyak, timeout agresif
    "checkout": {
        "max_concurrent_calls": 20,
        "max_wait_duration": 3.0,
    },
    "payment": {
        "max_concurrent_calls": 15,
        "max_wait_duration": 5.0,
    },
    # Service penting tapi bukan critical path
    "inventory": {
        "max_concurrent_calls": 10,
        "max_wait_duration": 2.0,
    },
    "search": {
        "max_concurrent_calls": 15,
        "max_wait_duration": 1.0,
    },
    # Service non-kritis — pool kecil, reject cepat jika penuh
    "recommendation": {
        "max_concurrent_calls": 5,
        "max_wait_duration": 0.5,
    },
    "review": {
        "max_concurrent_calls": 5,
        "max_wait_duration": 0.5,
    },
    "notification": {
        "max_concurrent_calls": 10,
        "max_wait_duration": 0.1,
    },
}


# ─────────────────────────────────────────────
# Domain Models
# ─────────────────────────────────────────────

@dataclass
class Order:
    order_id: str
    user_id: str
    items: list[str]
    total: float


@dataclass
class OrderResult:
    order_id: str
    success: bool
    message: str
    checkout_ms: float = 0.0
    payment_ms: float = 0.0
    # Fitur opsional — boleh gagal
    recommendation: Optional[list[str]] = None
    inventory_status: Optional[str] = None


# ─────────────────────────────────────────────
# Downstream Services (simulasi)
# ─────────────────────────────────────────────

class CheckoutService:
    """Service pemrosesan checkout — critical path."""

    def process(self, order: Order) -> dict:
        # Checkout biasanya cepat dan reliable
        processing_time = random.uniform(0.05, 0.2)
        time.sleep(processing_time)
        return {
            "status": "CONFIRMED",
            "order_id": order.order_id,
            "processing_ms": int(processing_time * 1000),
        }


class PaymentService:
    """Service pembayaran — critical path, bisa sedikit lambat."""

    def __init__(self, failure_rate: float = 0.05):
        self.failure_rate = failure_rate

    def charge(self, order: Order) -> dict:
        # Simulasi koneksi ke payment gateway (sedikit lambat)
        time.sleep(random.uniform(0.1, 0.4))
        if random.random() < self.failure_rate:
            raise Exception("Payment gateway timeout")
        return {
            "transaction_id": f"TXN-{order.order_id[-6:]}",
            "amount": order.total,
            "status": "PAID",
        }


class InventoryService:
    """Service pengecekan stok."""

    def check_stock(self, items: list[str]) -> dict:
        time.sleep(random.uniform(0.05, 0.15))
        return {item: random.randint(0, 100) for item in items}


class RecommendationService:
    """
    Service ML rekomendasi — NON-KRITIS.
    Saat flash sale, service ini bisa sangat lambat (model besar).
    """

    def __init__(self, slow_probability: float = 0.3):
        self.slow_probability = slow_probability

    def get_recommendations(self, user_id: str) -> list[str]:
        # Kadang sangat lambat (model inference)
        if random.random() < self.slow_probability:
            time.sleep(random.uniform(2.0, 5.0))  # sangat lambat!
        else:
            time.sleep(random.uniform(0.1, 0.3))

        return [f"Product-{i}" for i in random.sample(range(1, 100), 5)]


class ReviewService:
    """Service ulasan produk — non-kritis."""

    def get_recent_reviews(self, item_id: str) -> list[dict]:
        time.sleep(random.uniform(0.05, 0.3))
        return [{"rating": random.randint(1, 5), "text": "Produk bagus!"}
                for _ in range(3)]


class NotificationService:
    """Service notifikasi — fire and forget."""

    def send_order_confirmation(self, order_id: str, user_id: str) -> bool:
        time.sleep(random.uniform(0.05, 0.1))
        return True


# ─────────────────────────────────────────────
# E-Commerce Orchestrator dengan Bulkhead
# ─────────────────────────────────────────────

class ECommerceOrchestrator:
    """
    Orchestrator e-commerce yang menggunakan Bulkhead untuk isolasi service.

    Strategi:
    - Checkout & Payment: Pool besar, wait duration agak panjang (kritis)
    - Recommendation & Review: Pool kecil, fail-fast (non-kritis)
    - Degraded mode: Jika non-kritis gagal, tetap lanjutkan checkout
    """

    def __init__(self):
        self.registry = BulkheadRegistry()

        # Inisialisasi bulkhead per service
        self.bulkheads = {}
        for name, config in BULKHEAD_CONFIG.items():
            bh = ThreadPoolBulkhead(name=name, **config)
            self.bulkheads[name] = bh
            self.registry.register(bh)

        # Inisialisasi downstream services
        self.checkout_svc = CheckoutService()
        self.payment_svc = PaymentService(failure_rate=0.05)
        self.inventory_svc = InventoryService()
        self.recommendation_svc = RecommendationService(slow_probability=0.4)
        self.review_svc = ReviewService()
        self.notification_svc = NotificationService()

        self._stats = {
            "total_orders": 0,
            "successful_orders": 0,
            "failed_orders": 0,
            "degraded_orders": 0,  # sukses tapi fitur opsional gagal
        }
        self._stats_lock = threading.Lock()

    def process_order(self, order: Order) -> OrderResult:
        """
        Proses satu order lengkap dengan isolasi Bulkhead.

        Flow:
        1. Cek stok (penting, tapi boleh degraded)
        2. Proses checkout (WAJIB)
        3. Charge payment (WAJIB)
        4. Rekomendasi & Review (OPSIONAL — boleh gagal)
        5. Kirim notifikasi (fire-and-forget)
        """
        with self._stats_lock:
            self._stats["total_orders"] += 1

        result = OrderResult(
            order_id=order.order_id,
            success=False,
            message="",
        )
        is_degraded = False

        # ── Step 1: Cek Inventaris (penting tapi bukan blocker) ──
        try:
            inventory = self.bulkheads["inventory"].execute(
                self.inventory_svc.check_stock, order.items
            )
            result.inventory_status = "IN_STOCK"
            logger.debug(f"[{order.order_id}] Inventory OK: {inventory}")
        except BulkheadFullException:
            result.inventory_status = "UNKNOWN (bulkhead penuh)"
            is_degraded = True
            logger.warning(f"[{order.order_id}] Inventory bulkhead penuh — skip cek stok")
        except Exception as e:
            result.inventory_status = f"ERROR: {e}"
            is_degraded = True

        # ── Step 2: Proses Checkout (KRITIS — harus sukses) ──
        checkout_start = time.time()
        try:
            checkout_result = self.bulkheads["checkout"].execute(
                self.checkout_svc.process, order
            )
            result.checkout_ms = (time.time() - checkout_start) * 1000
            logger.info(f"[{order.order_id}] ✅ Checkout OK ({result.checkout_ms:.0f}ms)")
        except BulkheadFullException as e:
            result.message = f"Checkout tidak tersedia: {e}"
            result.checkout_ms = (time.time() - checkout_start) * 1000
            logger.error(f"[{order.order_id}] ❌ Checkout bulkhead penuh!")
            with self._stats_lock:
                self._stats["failed_orders"] += 1
            return result
        except Exception as e:
            result.message = f"Checkout gagal: {e}"
            logger.error(f"[{order.order_id}] ❌ Checkout error: {e}")
            with self._stats_lock:
                self._stats["failed_orders"] += 1
            return result

        # ── Step 3: Payment (KRITIS) ──
        payment_start = time.time()
        try:
            payment_result = self.bulkheads["payment"].execute(
                self.payment_svc.charge, order
            )
            result.payment_ms = (time.time() - payment_start) * 1000
            logger.info(
                f"[{order.order_id}] ✅ Payment OK — "
                f"TXN: {payment_result['transaction_id']} ({result.payment_ms:.0f}ms)"
            )
        except BulkheadFullException as e:
            result.message = f"Payment tidak tersedia: {e}"
            logger.error(f"[{order.order_id}] ❌ Payment bulkhead penuh!")
            with self._stats_lock:
                self._stats["failed_orders"] += 1
            return result
        except Exception as e:
            result.message = f"Payment gagal: {e}"
            logger.error(f"[{order.order_id}] ❌ Payment error: {e}")
            with self._stats_lock:
                self._stats["failed_orders"] += 1
            return result

        # ── Step 4: Enrichment OPSIONAL (boleh gagal) ──
        # Rekomendasi
        try:
            recs = self.bulkheads["recommendation"].execute(
                self.recommendation_svc.get_recommendations, order.user_id
            )
            result.recommendation = recs[:3]
        except BulkheadFullException:
            logger.info(f"[{order.order_id}] ⚠️  Rekomendasi: bulkhead penuh — skip")
            is_degraded = True
        except Exception as e:
            logger.info(f"[{order.order_id}] ⚠️  Rekomendasi: {e} — skip")
            is_degraded = True

        # ── Step 5: Notifikasi (fire-and-forget) ──
        try:
            self.bulkheads["notification"].execute(
                self.notification_svc.send_order_confirmation,
                order.order_id,
                order.user_id,
            )
            logger.debug(f"[{order.order_id}] 📧 Notifikasi terkirim")
        except (BulkheadFullException, Exception) as e:
            logger.debug(f"[{order.order_id}] 📧 Notifikasi gagal (diabaikan): {e}")

        # ── Sukses (dengan atau tanpa degradasi) ──
        result.success = True
        if is_degraded:
            result.message = "Order berhasil (mode degradasi — beberapa fitur tidak tersedia)"
            with self._stats_lock:
                self._stats["degraded_orders"] += 1
        else:
            result.message = "Order berhasil sepenuhnya"
            with self._stats_lock:
                self._stats["successful_orders"] += 1

        return result

    def print_final_report(self):
        """Cetak laporan akhir setelah simulasi selesai."""
        print("\n" + "=" * 70)
        print("📊 LAPORAN AKHIR E-COMMERCE SIMULATION")
        print("=" * 70)

        total = self._stats["total_orders"]
        success = self._stats["successful_orders"]
        degraded = self._stats["degraded_orders"]
        failed = self._stats["failed_orders"]

        print(f"\n📦 ORDERS:")
        print(f"  Total Order     : {total}")
        print(f"  ✅ Sukses penuh : {success} ({success/total*100:.1f}%)")
        print(f"  ⚠️  Degradasi    : {degraded} ({degraded/total*100:.1f}%)")
        print(f"  ❌ Gagal        : {failed} ({failed/total*100:.1f}%)")

        print(f"\n🔧 BULKHEAD METRICS:")
        for name, bh in self.bulkheads.items():
            m = bh.metrics
            print(
                f"  [{name:15s}] "
                f"Accepted: {m.total_accepted:4d} | "
                f"Rejected: {m.total_rejected:3d} ({m.rejection_rate:5.1f}%) | "
                f"Success: {m.total_success:4d} | "
                f"Fail: {m.total_failure:3d}"
            )
        print("=" * 70)

    def shutdown(self):
        """Cleanup semua thread pools."""
        self.registry.shutdown_all()


# ─────────────────────────────────────────────
# Simulasi Flash Sale
# ─────────────────────────────────────────────

def simulate_flash_sale(num_orders: int = 50, concurrency: int = 30):
    """
    Simulasi flash sale — banyak order datang bersamaan.

    Karakteristik flash sale:
    - Traffic spike sangat tiba-tiba (concurrency besar)
    - Recommendation service lambat (ML banyak request)
    - Checkout HARUS tetap jalan
    """
    print("\n" + "═" * 70)
    print(f"🛍️  FLASH SALE SIMULATION")
    print(f"   {num_orders} orders × {concurrency} concurrent threads")
    print("═" * 70)

    orchestrator = ECommerceOrchestrator()
    orders = [
        Order(
            order_id=f"ORD-{i:05d}",
            user_id=f"USR-{i % 100:03d}",
            items=[f"ITEM-{j}" for j in random.sample(range(1, 50), random.randint(1, 5))],
            total=round(random.uniform(50_000, 2_000_000), 0),
        )
        for i in range(1, num_orders + 1)
    ]

    results: list[OrderResult] = []
    results_lock = threading.Lock()

    def process_single(order: Order):
        result = orchestrator.process_order(order)
        with results_lock:
            results.append(result)

    # Proses semua order secara concurrent (simulasi traffic spike)
    start = time.time()
    threads = [threading.Thread(target=process_single, args=(order,)) for order in orders]

    # Batasi concurrency simulasi menggunakan semaphore
    concurrency_sem = threading.Semaphore(concurrency)

    def limited_process(order: Order):
        with concurrency_sem:
            process_single(order)

    threads = [threading.Thread(target=limited_process, args=(order,)) for order in orders]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    elapsed = time.time() - start

    # Statistik hasil
    success = [r for r in results if r.success and "degradasi" not in r.message]
    degraded = [r for r in results if r.success and "degradasi" in r.message]
    failed = [r for r in results if not r.success]
    has_recs = [r for r in results if r.recommendation]

    print(f"\n⏱️  Selesai dalam {elapsed:.1f} detik")
    print(f"📦 Total orders: {len(results)}")
    print(f"   ✅ Sukses penuh  : {len(success)}")
    print(f"   ⚠️  Degradasi     : {len(degraded)}")
    print(f"   ❌ Gagal         : {len(failed)}")
    print(f"   📝 Dapat rekomend: {len(has_recs)}")

    if failed:
        print(f"\n❌ Contoh order gagal:")
        for r in failed[:3]:
            print(f"   [{r.order_id}] {r.message}")

    orchestrator.print_final_report()
    orchestrator.shutdown()


def simulate_service_degradation():
    """
    Simulasi: Recommendation service mati total.
    Tunjukkan bahwa Checkout tetap berjalan normal.
    """
    print("\n" + "═" * 70)
    print("🔥 SIMULASI: RECOMMENDATION SERVICE SANGAT LAMBAT")
    print("   (Checkout harus tetap jalan — Bulkhead memastikan ini)")
    print("═" * 70)

    checkout_bh = ThreadPoolBulkhead("checkout", max_concurrent_calls=10, max_wait_duration=2.0)
    recommend_bh = ThreadPoolBulkhead("recommendation", max_concurrent_calls=3, max_wait_duration=0.5)

    checkout_results = []
    recommend_results = []
    lock = threading.Lock()

    def do_checkout(i):
        try:
            result = checkout_bh.execute(lambda: (time.sleep(0.1), f"Order {i} OK")[1])
            with lock:
                checkout_results.append(f"✅ Checkout {i}")
        except BulkheadFullException:
            with lock:
                checkout_results.append(f"❌ Checkout {i} DITOLAK")

    def do_recommendation(i):
        try:
            # Recommendation sangat lambat (3 detik)
            result = recommend_bh.execute(lambda: (time.sleep(3.0), f"Rec {i}")[1])
            with lock:
                recommend_results.append(f"✅ Recommendation {i}")
        except BulkheadFullException:
            with lock:
                recommend_results.append(f"⚠️  Recommendation {i} ditolak (terisolasi!)")

    # Launch 5 recommendation requests (akan memblokir recommendation pool)
    # dan 5 checkout requests (harus tetap sukses)
    threads = []
    for i in range(5):
        threads.append(threading.Thread(target=do_recommendation, args=(i,)))
    for i in range(5):
        threads.append(threading.Thread(target=do_checkout, args=(i,)))

    for t in threads:
        t.start()

    # Tunggu 1.5 detik (cukup untuk checkout selesai tapi recommendation belum)
    time.sleep(1.5)

    print("\n📊 Status setelah 1.5 detik:")
    print(f"   Checkout Pool  : {checkout_bh.active_count}/{checkout_bh.max_concurrent_calls} active")
    print(f"   Recommend Pool : {recommend_bh.active_count}/{recommend_bh.max_concurrent_calls} active")
    print(f"\n   Checkout Results: {checkout_results}")
    print(f"   Recommend Results: {recommend_results}")
    print("\n   ✅ Checkout selesai cepat meskipun Recommendation lambat!")
    print("   ✅ Bulkhead berhasil mengisolasi — tidak ada cascading failure!")

    for t in threads:
        t.join(timeout=5.0)

    checkout_bh.shutdown()
    recommend_bh.shutdown()


# ─────────────────────────────────────────────
# Entrypoint
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 70)
    print("E-COMMERCE BULKHEAD PATTERN — DEMO LENGKAP")
    print("=" * 70)

    # Demo 1: Service degradation isolation
    simulate_service_degradation()

    # Demo 2: Flash sale simulation
    simulate_flash_sale(num_orders=40, concurrency=20)

    print("\n✅ Semua simulasi selesai!")
    print("Pesan kunci:")
    print("  1. Kegagalan di non-critical service TERISOLASI")
    print("  2. Critical path (Checkout) SELALU berjalan")
    print("  3. Sistem tetap memberikan value meski dalam kondisi degradasi")
