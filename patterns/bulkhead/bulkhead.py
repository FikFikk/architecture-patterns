"""
Bulkhead Pattern — Core Implementation
=======================================
Implementasi Thread Pool Bulkhead dan Semaphore Bulkhead dalam Python.

Pola ini mengisolasi resource (thread, koneksi) per service/group sehingga
kegagalan atau overload di satu partisi tidak memengaruhi partisi lain.

Penggunaan:
    python bulkhead.py
"""

import threading
import time
import random
import logging
import uuid
from concurrent.futures import ThreadPoolExecutor, Future
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Any, Optional
from queue import Queue, Full, Empty

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("bulkhead")


# ─────────────────────────────────────────────
# Exception
# ─────────────────────────────────────────────

class BulkheadFullException(Exception):
    """Dilempar saat partisi Bulkhead sudah penuh dan tidak bisa menerima request baru."""


class BulkheadTimeoutException(Exception):
    """Dilempar saat request menunggu terlalu lama di antrian Bulkhead."""


# ─────────────────────────────────────────────
# Metrics
# ─────────────────────────────────────────────

@dataclass
class BulkheadMetrics:
    """Statistik performa sebuah partisi Bulkhead."""
    name: str
    total_accepted: int = 0
    total_rejected: int = 0
    total_success: int = 0
    total_failure: int = 0
    total_timeout: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    @property
    def total_calls(self) -> int:
        return self.total_accepted + self.total_rejected

    @property
    def rejection_rate(self) -> float:
        if self.total_calls == 0:
            return 0.0
        return self.total_rejected / self.total_calls * 100

    @property
    def success_rate(self) -> float:
        if self.total_accepted == 0:
            return 0.0
        return self.total_success / self.total_accepted * 100

    def record_accepted(self):
        with self._lock:
            self.total_accepted += 1

    def record_rejected(self):
        with self._lock:
            self.total_rejected += 1

    def record_success(self):
        with self._lock:
            self.total_success += 1

    def record_failure(self):
        with self._lock:
            self.total_failure += 1

    def record_timeout(self):
        with self._lock:
            self.total_timeout += 1

    def summary(self) -> str:
        return (
            f"[{self.name}] "
            f"Total calls: {self.total_calls} | "
            f"Accepted: {self.total_accepted} | "
            f"Rejected: {self.total_rejected} ({self.rejection_rate:.1f}%) | "
            f"Success: {self.total_success} | "
            f"Failure: {self.total_failure} | "
            f"Timeout: {self.total_timeout} | "
            f"Success rate: {self.success_rate:.1f}%"
        )


# ─────────────────────────────────────────────
# Thread Pool Bulkhead
# ─────────────────────────────────────────────

class ThreadPoolBulkhead:
    """
    Thread Pool Bulkhead — memberikan thread pool terdedikasi per partisi.

    Setiap instance Bulkhead memiliki:
    - Thread pool sendiri (max_concurrent_calls thread)
    - Antrian sendiri (max_wait_duration dan max_concurrent_calls)
    - Metrik sendiri

    Kegagalan/overload di satu Bulkhead tidak memengaruhi yang lain.
    """

    def __init__(
        self,
        name: str,
        max_concurrent_calls: int = 10,
        max_wait_duration: float = 5.0,  # detik
    ):
        """
        Args:
            name: Nama identifikasi partisi
            max_concurrent_calls: Jumlah maksimum thread concurrent
            max_wait_duration: Waktu tunggu maksimum (detik) jika pool penuh
        """
        self.name = name
        self.max_concurrent_calls = max_concurrent_calls
        self.max_wait_duration = max_wait_duration
        self.metrics = BulkheadMetrics(name)
        self._executor = ThreadPoolExecutor(
            max_workers=max_concurrent_calls,
            thread_name_prefix=f"bulkhead-{name}"
        )
        self._semaphore = threading.Semaphore(max_concurrent_calls)
        self._lock = threading.Lock()
        self._active_count = 0
        self._logger = logging.getLogger(f"bulkhead.{name}")
        self._logger.info(
            f"Bulkhead '{name}' dibuat — max_concurrent: {max_concurrent_calls}, "
            f"max_wait: {max_wait_duration}s"
        )

    @property
    def active_count(self) -> int:
        """Jumlah thread yang sedang aktif."""
        return self._active_count

    @property
    def is_full(self) -> bool:
        """True jika pool penuh (tidak bisa menerima request baru tanpa menunggu)."""
        return self._active_count >= self.max_concurrent_calls

    def execute(self, func: Callable, *args, **kwargs) -> Any:
        """
        Eksekusi fungsi dalam thread pool Bulkhead ini.

        Args:
            func: Fungsi yang akan dieksekusi
            *args, **kwargs: Argumen untuk fungsi

        Returns:
            Hasil dari fungsi

        Raises:
            BulkheadFullException: Jika tidak dapat slot dalam max_wait_duration
            BulkheadTimeoutException: Jika eksekusi melebihi batas waktu
        """
        # Coba acquire semaphore dalam batas waktu
        acquired = self._semaphore.acquire(timeout=self.max_wait_duration)
        if not acquired:
            self.metrics.record_rejected()
            self._logger.warning(
                f"Bulkhead '{self.name}' PENUH! Request ditolak. "
                f"Active: {self._active_count}/{self.max_concurrent_calls}"
            )
            raise BulkheadFullException(
                f"Bulkhead '{self.name}' penuh. "
                f"Coba lagi nanti atau hubungi administrator."
            )

        # Slot tersedia — jalankan
        self.metrics.record_accepted()
        with self._lock:
            self._active_count += 1

        self._logger.debug(
            f"Request diterima — Active: {self._active_count}/{self.max_concurrent_calls}"
        )

        try:
            result = func(*args, **kwargs)
            self.metrics.record_success()
            return result
        except Exception as e:
            self.metrics.record_failure()
            raise
        finally:
            with self._lock:
                self._active_count -= 1
            self._semaphore.release()

    def submit(self, func: Callable, *args, **kwargs) -> Future:
        """
        Submit fungsi untuk dieksekusi secara asinkron.

        Returns:
            Future yang dapat di-.result() untuk mendapatkan nilai kembalian.
        """
        # Cek kapasitas secara non-blocking untuk fail-fast
        acquired = self._semaphore.acquire(blocking=False)
        if not acquired:
            self.metrics.record_rejected()
            raise BulkheadFullException(
                f"Bulkhead '{self.name}' penuh — submit ditolak"
            )

        self.metrics.record_accepted()
        with self._lock:
            self._active_count += 1

        def wrapper():
            try:
                result = func(*args, **kwargs)
                self.metrics.record_success()
                return result
            except Exception:
                self.metrics.record_failure()
                raise
            finally:
                with self._lock:
                    self._active_count -= 1
                self._semaphore.release()

        return self._executor.submit(wrapper)

    def shutdown(self, wait: bool = True):
        """Matikan Bulkhead dan tunggu semua thread selesai."""
        self._executor.shutdown(wait=wait)

    def __repr__(self) -> str:
        return (
            f"ThreadPoolBulkhead(name='{self.name}', "
            f"active={self._active_count}/{self.max_concurrent_calls})"
        )

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.shutdown()


# ─────────────────────────────────────────────
# Semaphore Bulkhead (lebih ringan)
# ─────────────────────────────────────────────

class SemaphoreBulkhead:
    """
    Semaphore Bulkhead — membatasi jumlah concurrent calls menggunakan semaphore.

    Lebih ringan dari ThreadPoolBulkhead karena tidak membuat thread baru;
    hanya membatasi berapa banyak call yang bisa berjalan paralel
    dalam thread pool yang sudah ada.

    Cocok untuk:
    - I/O bound operations dalam async framework
    - Operasi yang sudah punya thread pool sendiri (FastAPI, dsb)
    - Limiting concurrent external API calls
    """

    def __init__(
        self,
        name: str,
        max_concurrent_calls: int = 10,
        max_wait_duration: float = 0.0,  # 0 = fail-fast (tidak menunggu)
    ):
        self.name = name
        self.max_concurrent_calls = max_concurrent_calls
        self.max_wait_duration = max_wait_duration
        self.metrics = BulkheadMetrics(name)
        self._semaphore = threading.Semaphore(max_concurrent_calls)
        self._active = 0
        self._lock = threading.Lock()
        self._logger = logging.getLogger(f"bulkhead.semaphore.{name}")

    @property
    def active_count(self) -> int:
        return self._active

    @property
    def available_permits(self) -> int:
        return self.max_concurrent_calls - self._active

    def __call__(self, func: Callable) -> Callable:
        """Gunakan sebagai decorator."""
        def wrapper(*args, **kwargs):
            return self.execute(func, *args, **kwargs)
        wrapper.__name__ = func.__name__
        return wrapper

    def execute(self, func: Callable, *args, **kwargs) -> Any:
        """Eksekusi fungsi dengan pembatasan concurrent calls."""
        # Untuk fail-fast: blocking=False
        # Untuk wait: blocking=True, timeout=max_wait_duration
        if self.max_wait_duration <= 0:
            acquired = self._semaphore.acquire(blocking=False)
        else:
            acquired = self._semaphore.acquire(timeout=self.max_wait_duration)

        if not acquired:
            self.metrics.record_rejected()
            raise BulkheadFullException(
                f"Semaphore Bulkhead '{self.name}' penuh "
                f"({self._active}/{self.max_concurrent_calls} concurrent calls)"
            )

        self.metrics.record_accepted()
        with self._lock:
            self._active += 1

        try:
            result = func(*args, **kwargs)
            self.metrics.record_success()
            return result
        except Exception:
            self.metrics.record_failure()
            raise
        finally:
            with self._lock:
                self._active -= 1
            self._semaphore.release()

    def __repr__(self) -> str:
        return (
            f"SemaphoreBulkhead('{self.name}', "
            f"active={self._active}/{self.max_concurrent_calls})"
        )


# ─────────────────────────────────────────────
# Bulkhead Registry (mengelola banyak bulkhead)
# ─────────────────────────────────────────────

class BulkheadRegistry:
    """
    Registry untuk mengelola beberapa Bulkhead sekaligus.
    Berguna untuk monitoring terpusat dan konfigurasi.
    """

    def __init__(self):
        self._bulkheads: dict[str, ThreadPoolBulkhead | SemaphoreBulkhead] = {}
        self._lock = threading.Lock()

    def register(self, bulkhead) -> None:
        """Daftarkan sebuah bulkhead ke registry."""
        with self._lock:
            self._bulkheads[bulkhead.name] = bulkhead

    def get(self, name: str):
        """Ambil bulkhead berdasarkan nama."""
        return self._bulkheads.get(name)

    def get_or_create(
        self,
        name: str,
        max_concurrent_calls: int = 10,
        max_wait_duration: float = 5.0,
        bulkhead_type: str = "thread_pool",
    ):
        """Ambil bulkhead yang sudah ada atau buat baru."""
        with self._lock:
            if name not in self._bulkheads:
                if bulkhead_type == "semaphore":
                    bh = SemaphoreBulkhead(name, max_concurrent_calls, max_wait_duration)
                else:
                    bh = ThreadPoolBulkhead(name, max_concurrent_calls, max_wait_duration)
                self._bulkheads[name] = bh
            return self._bulkheads[name]

    def all_metrics(self) -> list[BulkheadMetrics]:
        """Ambil metrics semua bulkhead yang terdaftar."""
        return [bh.metrics for bh in self._bulkheads.values()]

    def print_report(self):
        """Cetak laporan metrics semua bulkhead."""
        print("\n" + "=" * 80)
        print("BULKHEAD METRICS REPORT")
        print("=" * 80)
        for metrics in self.all_metrics():
            print(metrics.summary())
        print("=" * 80)

    def shutdown_all(self):
        """Matikan semua bulkhead."""
        for bh in self._bulkheads.values():
            if hasattr(bh, "shutdown"):
                bh.shutdown()


# ─────────────────────────────────────────────
# Decorator helper
# ─────────────────────────────────────────────

def bulkhead(
    name: str,
    max_concurrent_calls: int = 10,
    max_wait_duration: float = 5.0,
    registry: Optional[BulkheadRegistry] = None,
):
    """
    Decorator yang membungkus fungsi dalam Thread Pool Bulkhead.

    Contoh:
        @bulkhead("payment-service", max_concurrent_calls=20)
        def call_payment_api(order_id):
            ...
    """
    def decorator(func: Callable) -> Callable:
        _registry = registry or BulkheadRegistry()
        _bulkhead = _registry.get_or_create(
            name, max_concurrent_calls, max_wait_duration
        )

        def wrapper(*args, **kwargs):
            return _bulkhead.execute(func, *args, **kwargs)

        wrapper.__name__ = func.__name__
        wrapper.__doc__ = func.__doc__
        wrapper._bulkhead = _bulkhead
        return wrapper

    return decorator


# ─────────────────────────────────────────────
# Demo: Simulasi cascading failure vs bulkhead
# ─────────────────────────────────────────────

def simulate_slow_service(name: str, delay: float = 0.5):
    """Simulasi service yang lambat."""
    time.sleep(delay)
    return f"{name}: selesai setelah {delay:.1f}s"


def demo_without_bulkhead():
    """Demo: apa yang terjadi tanpa bulkhead — cascading failure."""
    print("\n" + "=" * 60)
    print("DEMO 1: TANPA BULKHEAD (Shared Thread Pool)")
    print("=" * 60)

    shared_pool = ThreadPoolExecutor(max_workers=10, thread_name_prefix="shared")
    results = {"checkout": [], "recommend": [], "review": []}
    start = time.time()

    futures = []

    # Simulate: Recommendation service jadi sangat lambat (menghabiskan thread)
    for i in range(8):
        f = shared_pool.submit(simulate_slow_service, "Recommendation", 3.0)
        futures.append(("recommend", f))

    # Checkout dan Review tidak bisa dapat thread karena sudah habis!
    for i in range(5):
        f = shared_pool.submit(simulate_slow_service, "Checkout", 0.1)
        futures.append(("checkout", f))

    for i in range(3):
        f = shared_pool.submit(simulate_slow_service, "Review", 0.1)
        futures.append(("review", f))

    # Kumpulkan hasil
    for service, future in futures:
        try:
            result = future.result(timeout=5.0)
            results[service].append("✅ OK")
        except Exception as e:
            results[service].append(f"❌ {e}")

    elapsed = time.time() - start
    shared_pool.shutdown(wait=False)

    print(f"\nWaktu total: {elapsed:.1f}s")
    print(f"Checkout:       {results['checkout']}")
    print(f"Recommendation: {results['recommend'][:3]}... ({len(results['recommend'])} total)")
    print(f"Review:         {results['review']}")
    print("\n⚠️  Checkout TERLAMBAT karena thread dihabiskan oleh Recommendation!")


def demo_with_bulkhead():
    """Demo: dengan bulkhead — kegagalan terisolasi."""
    print("\n" + "=" * 60)
    print("DEMO 2: DENGAN BULKHEAD (Thread Pool Terisolasi)")
    print("=" * 60)

    # Setiap service mendapat thread pool sendiri
    checkout_bh = ThreadPoolBulkhead("checkout", max_concurrent_calls=10, max_wait_duration=2.0)
    recommend_bh = ThreadPoolBulkhead("recommendation", max_concurrent_calls=5, max_wait_duration=0.5)
    review_bh = ThreadPoolBulkhead("review", max_concurrent_calls=5, max_wait_duration=1.0)

    results = {"checkout": [], "recommend": [], "review": []}
    start = time.time()
    all_threads = []

    def run_checkout(i):
        try:
            result = checkout_bh.execute(simulate_slow_service, "Checkout", 0.1)
            results["checkout"].append("✅ OK")
        except BulkheadFullException:
            results["checkout"].append("⛔ BH Full")

    def run_recommend(i):
        try:
            # Recommendation service jadi lambat
            result = recommend_bh.execute(simulate_slow_service, "Recommendation", 3.0)
            results["recommend"].append("✅ OK")
        except BulkheadFullException:
            results["recommend"].append("⛔ BH Full (terisolasi!)")

    def run_review(i):
        try:
            result = review_bh.execute(simulate_slow_service, "Review", 0.1)
            results["review"].append("✅ OK")
        except BulkheadFullException:
            results["review"].append("⛔ BH Full")

    # Jalankan semua secara concurrent
    for i in range(8):
        t = threading.Thread(target=run_recommend, args=(i,))
        all_threads.append(t)
    for i in range(5):
        t = threading.Thread(target=run_checkout, args=(i,))
        all_threads.append(t)
    for i in range(3):
        t = threading.Thread(target=run_review, args=(i,))
        all_threads.append(t)

    for t in all_threads:
        t.start()

    # Tunggu thread checkout dan review (yang cepat) selesai
    time.sleep(1.0)

    print(f"\nStatus setelah 1 detik:")
    print(f"Checkout ({checkout_bh.active_count} active): {results['checkout']}")
    print(f"Recommendation ({recommend_bh.active_count} active): {results['recommend']}")
    print(f"Review ({review_bh.active_count} active):   {results['review']}")
    print("\n✅ Checkout & Review SELESAI CEPAT meskipun Recommendation lambat!")
    print("✅ Bulkhead berhasil mengisolasi kegagalan!")

    # Cetak metrics
    for bh in [checkout_bh, recommend_bh, review_bh]:
        print(f"  {bh.metrics.summary()}")

    # Cleanup
    for t in all_threads:
        t.join(timeout=4.0)
    checkout_bh.shutdown()
    recommend_bh.shutdown()
    review_bh.shutdown()


def demo_semaphore_bulkhead():
    """Demo: Semaphore Bulkhead untuk API calls bersamaan."""
    print("\n" + "=" * 60)
    print("DEMO 3: SEMAPHORE BULKHEAD (Fail-Fast)")
    print("=" * 60)

    # Batas 3 concurrent calls ke Payment API
    payment_bh = SemaphoreBulkhead(
        name="payment-api",
        max_concurrent_calls=3,
        max_wait_duration=0.0,  # fail-fast
    )

    results = []
    lock = threading.Lock()

    def call_payment_api(order_id: str):
        def _payment():
            time.sleep(0.5)  # simulasi call ke payment gateway
            return {"status": "SUCCESS", "order_id": order_id}

        try:
            result = payment_bh.execute(_payment)
            with lock:
                results.append(f"Order {order_id}: ✅ {result['status']}")
        except BulkheadFullException as e:
            with lock:
                results.append(f"Order {order_id}: ⛔ DITOLAK (concurrent limit)")

    # 8 order masuk bersamaan — hanya 3 bisa diproses simultaneous
    threads = [
        threading.Thread(target=call_payment_api, args=(f"ORD-{i:03d}",))
        for i in range(1, 9)
    ]

    for t in threads:
        t.start()
    for t in threads:
        t.join()

    print("\nHasil 8 concurrent payment requests (max 3 simultaneous):")
    for r in sorted(results):
        print(f"  {r}")
    print(f"\nMetrics: {payment_bh.metrics.summary()}")


# ─────────────────────────────────────────────
# Entrypoint
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("BULKHEAD PATTERN — Demo")
    print("=" * 60)

    demo_without_bulkhead()
    demo_with_bulkhead()
    demo_semaphore_bulkhead()

    print("\n" + "=" * 60)
    print("Demo selesai!")
    print("Jalankan: pytest test_bulkhead.py -v untuk unit tests")
    print("Jalankan: python example_ecommerce.py untuk studi kasus lengkap")
    print("=" * 60)
