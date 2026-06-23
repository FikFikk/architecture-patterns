"""
Bulkhead Pattern — Unit & Integration Tests
===========================================
Test coverage untuk:
- ThreadPoolBulkhead basic operations
- SemaphoreBulkhead basic operations
- Isolation behavior (bulkhead satu tidak memengaruhi yang lain)
- Metrics accuracy
- BulkheadRegistry
- Decorator usage
- Edge cases

Penggunaan:
    pytest test_bulkhead.py -v
    pytest test_bulkhead.py -v --tb=short
"""

import threading
import time
import pytest
from concurrent.futures import ThreadPoolExecutor

from bulkhead import (
    ThreadPoolBulkhead,
    SemaphoreBulkhead,
    BulkheadRegistry,
    BulkheadFullException,
    BulkheadMetrics,
    bulkhead,
)


# ─────────────────────────────────────────────
# Fixtures & Helpers
# ─────────────────────────────────────────────

def fast_task(result="OK", delay=0.01):
    """Task cepat untuk pengujian."""
    time.sleep(delay)
    return result


def slow_task(delay=2.0):
    """Task lambat yang akan memblokir thread."""
    time.sleep(delay)
    return "slow_done"


def failing_task():
    """Task yang selalu gagal."""
    raise ValueError("Task gagal!")


# ─────────────────────────────────────────────
# Tests: ThreadPoolBulkhead — Basic
# ─────────────────────────────────────────────

class TestThreadPoolBulkheadBasic:
    """Unit test untuk ThreadPoolBulkhead — fungsionalitas dasar."""

    def test_successful_execution(self):
        """Bulkhead berhasil mengeksekusi fungsi dan mengembalikan hasil."""
        bh = ThreadPoolBulkhead("test-basic", max_concurrent_calls=5)
        result = bh.execute(fast_task, "hello")
        assert result == "hello"
        bh.shutdown()

    def test_metrics_track_success(self):
        """Metrics tracking: accepted dan success bertambah setelah eksekusi sukses."""
        bh = ThreadPoolBulkhead("test-metrics-success", max_concurrent_calls=5)
        bh.execute(fast_task, "x")
        bh.execute(fast_task, "y")

        assert bh.metrics.total_accepted == 2
        assert bh.metrics.total_success == 2
        assert bh.metrics.total_rejected == 0
        assert bh.metrics.total_failure == 0
        bh.shutdown()

    def test_metrics_track_failure(self):
        """Metrics tracking: failure bertambah saat task raise exception."""
        bh = ThreadPoolBulkhead("test-metrics-fail", max_concurrent_calls=5)

        with pytest.raises(ValueError):
            bh.execute(failing_task)

        assert bh.metrics.total_accepted == 1
        assert bh.metrics.total_success == 0
        assert bh.metrics.total_failure == 1
        bh.shutdown()

    def test_rejected_when_full(self):
        """BulkheadFullException saat pool penuh dan tidak ada slot kosong."""
        bh = ThreadPoolBulkhead(
            "test-reject",
            max_concurrent_calls=2,
            max_wait_duration=0.1,  # tunggu singkat lalu reject
        )

        # Isi pool dengan slow tasks
        t1 = threading.Thread(target=bh.execute, args=(slow_task,), kwargs={"delay": 2.0})
        t2 = threading.Thread(target=bh.execute, args=(slow_task,), kwargs={"delay": 2.0})
        t1.start()
        t2.start()
        time.sleep(0.05)  # pastikan kedua thread sudah mulai

        # Request ke-3 harus ditolak
        with pytest.raises(BulkheadFullException):
            bh.execute(fast_task)

        assert bh.metrics.total_rejected >= 1

        t1.join(timeout=3.0)
        t2.join(timeout=3.0)
        bh.shutdown()

    def test_metrics_rejection_rate(self):
        """Rejection rate dihitung dengan benar."""
        bh = ThreadPoolBulkhead(
            "test-reject-rate",
            max_concurrent_calls=1,
            max_wait_duration=0.05,
        )

        # 1 task lambat mengisi pool
        t = threading.Thread(target=bh.execute, args=(slow_task,), kwargs={"delay": 1.0})
        t.start()
        time.sleep(0.05)

        # 2 request ditolak
        for _ in range(2):
            try:
                bh.execute(fast_task)
            except BulkheadFullException:
                pass

        # 1 accepted, 2 rejected → rejection_rate = 2/3 * 100 ≈ 66.7%
        assert bh.metrics.total_accepted == 1
        assert bh.metrics.total_rejected == 2
        assert abs(bh.metrics.rejection_rate - 66.67) < 1.0

        t.join(timeout=2.0)
        bh.shutdown()

    def test_exception_propagation(self):
        """Exception dari task harus propagate ke caller."""
        bh = ThreadPoolBulkhead("test-exception", max_concurrent_calls=5)

        with pytest.raises(ValueError, match="Task gagal"):
            bh.execute(failing_task)

        bh.shutdown()

    def test_context_manager(self):
        """Bulkhead bisa digunakan sebagai context manager."""
        with ThreadPoolBulkhead("test-ctx", max_concurrent_calls=3) as bh:
            result = bh.execute(fast_task, "ctx_result")
            assert result == "ctx_result"
        # Setelah exit, executor sudah di-shutdown

    def test_active_count_decrements_after_task(self):
        """active_count berkurang setelah task selesai."""
        bh = ThreadPoolBulkhead("test-active", max_concurrent_calls=5)
        bh.execute(fast_task)
        # Setelah selesai, active_count harus kembali ke 0
        time.sleep(0.05)
        assert bh.active_count == 0
        bh.shutdown()

    def test_repr(self):
        """__repr__ menampilkan informasi yang benar."""
        bh = ThreadPoolBulkhead("test-repr", max_concurrent_calls=10)
        r = repr(bh)
        assert "test-repr" in r
        assert "10" in r
        bh.shutdown()


# ─────────────────────────────────────────────
# Tests: Isolation (Kunci dari Bulkhead Pattern)
# ─────────────────────────────────────────────

class TestBulkheadIsolation:
    """
    Test inti: kegagalan/overload di satu Bulkhead tidak memengaruhi yang lain.
    Ini adalah tujuan utama dari Bulkhead Pattern.
    """

    def test_slow_service_does_not_block_other_bulkhead(self):
        """
        Jika Service A lambat dan mengorbankan pool-nya,
        Service B (pool terpisah) tetap berjalan normal.
        """
        # Service A: pool kecil
        bh_a = ThreadPoolBulkhead("svc-a", max_concurrent_calls=3, max_wait_duration=0.5)
        # Service B: pool terpisah
        bh_b = ThreadPoolBulkhead("svc-b", max_concurrent_calls=5, max_wait_duration=2.0)

        b_results = []
        b_lock = threading.Lock()

        def fill_a_pool():
            """Isi pool A dengan slow tasks."""
            try:
                bh_a.execute(slow_task, delay=2.0)
            except Exception:
                pass

        def call_b():
            """Eksekusi di pool B — harus tetap cepat."""
            try:
                result = bh_b.execute(fast_task, "B_result", delay=0.05)
                with b_lock:
                    b_results.append(result)
            except Exception as e:
                with b_lock:
                    b_results.append(f"ERROR: {e}")

        # Isi pool A penuh
        a_threads = [threading.Thread(target=fill_a_pool) for _ in range(3)]
        for t in a_threads:
            t.start()
        time.sleep(0.1)  # pastikan pool A sudah terisi

        # Sekarang Pool A penuh — pool B harus tetap berjalan
        b_threads = [threading.Thread(target=call_b) for _ in range(5)]
        b_start = time.time()
        for t in b_threads:
            t.start()
        for t in b_threads:
            t.join(timeout=2.0)
        b_elapsed = time.time() - b_start

        # Pool B harus selesai dengan cepat (< 0.5 detik, bukan 2 detik)
        assert b_elapsed < 0.5, f"Pool B terlalu lambat: {b_elapsed:.2f}s (terpengaruh pool A?)"
        assert all(r == "B_result" for r in b_results), f"Beberapa B request gagal: {b_results}"
        assert len(b_results) == 5

        for t in a_threads:
            t.join(timeout=3.0)
        bh_a.shutdown()
        bh_b.shutdown()

    def test_rejected_in_a_does_not_affect_b(self):
        """
        Request yang ditolak di Bulkhead A tidak memengaruhi Bulkhead B.
        """
        bh_a = ThreadPoolBulkhead("reject-a", max_concurrent_calls=1, max_wait_duration=0.05)
        bh_b = ThreadPoolBulkhead("reject-b", max_concurrent_calls=5, max_wait_duration=1.0)

        # Isi pool A
        t = threading.Thread(target=bh_a.execute, args=(slow_task,), kwargs={"delay": 1.0})
        t.start()
        time.sleep(0.05)

        # Pool A reject
        with pytest.raises(BulkheadFullException):
            bh_a.execute(fast_task)

        # Pool B tidak terpengaruh
        result = bh_b.execute(fast_task, "B_ok")
        assert result == "B_ok"

        # Metrics terpisah
        assert bh_a.metrics.total_rejected == 1
        assert bh_b.metrics.total_rejected == 0

        t.join(timeout=2.0)
        bh_a.shutdown()
        bh_b.shutdown()

    def test_three_isolated_pools(self):
        """
        Tiga pool terisolasi: overload di satu tidak memengaruhi dua yang lain.
        Mensimulasikan Checkout + Rekomendasi + Review di e-commerce.
        """
        checkout_bh = ThreadPoolBulkhead("checkout", max_concurrent_calls=5, max_wait_duration=2.0)
        recommend_bh = ThreadPoolBulkhead("recommend", max_concurrent_calls=2, max_wait_duration=0.1)
        review_bh = ThreadPoolBulkhead("review", max_concurrent_calls=3, max_wait_duration=1.0)

        checkout_success = []
        review_success = []
        recommend_rejected = []
        lock = threading.Lock()

        def block_recommend():
            try:
                recommend_bh.execute(slow_task, delay=2.0)
            except Exception:
                pass

        def do_checkout(i):
            try:
                r = checkout_bh.execute(fast_task, f"order_{i}", delay=0.05)
                with lock:
                    checkout_success.append(r)
            except Exception:
                pass

        def do_review(i):
            try:
                r = review_bh.execute(fast_task, f"review_{i}", delay=0.05)
                with lock:
                    review_success.append(r)
            except Exception:
                pass

        def do_recommend_excess(i):
            try:
                recommend_bh.execute(fast_task)
            except BulkheadFullException:
                with lock:
                    recommend_rejected.append(i)

        threads = []

        # Isi pool rekomendasi (2/2 penuh)
        for _ in range(2):
            threads.append(threading.Thread(target=block_recommend))

        for t in threads[:2]:
            t.start()
        time.sleep(0.1)

        # Checkout & Review harus jalan normal
        for i in range(5):
            threads.append(threading.Thread(target=do_checkout, args=(i,)))
        for i in range(3):
            threads.append(threading.Thread(target=do_review, args=(i,)))

        # Request extra ke recommend yang sudah penuh
        for i in range(3):
            threads.append(threading.Thread(target=do_recommend_excess, args=(i,)))

        for t in threads[2:]:
            t.start()
        for t in threads:
            t.join(timeout=3.0)

        assert len(checkout_success) == 5, f"Checkout seharusnya 5, dapat: {len(checkout_success)}"
        assert len(review_success) == 3, f"Review seharusnya 3, dapat: {len(review_success)}"
        assert len(recommend_rejected) == 3, f"Rekomendasi seharusnya 3 ditolak"

        checkout_bh.shutdown()
        recommend_bh.shutdown()
        review_bh.shutdown()


# ─────────────────────────────────────────────
# Tests: SemaphoreBulkhead
# ─────────────────────────────────────────────

class TestSemaphoreBulkhead:

    def test_successful_execution(self):
        """SemaphoreBulkhead berhasil eksekusi dalam batas concurrent."""
        bh = SemaphoreBulkhead("sema-basic", max_concurrent_calls=5)
        result = bh.execute(fast_task, "sema_result")
        assert result == "sema_result"

    def test_fail_fast_when_full(self):
        """Semaphore Bulkhead fail-fast (max_wait_duration=0) saat penuh."""
        bh = SemaphoreBulkhead(
            "sema-reject",
            max_concurrent_calls=2,
            max_wait_duration=0.0,  # fail-fast
        )

        # Isi 2 slot yang tersedia
        barrier = threading.Barrier(3)
        results = []
        lock = threading.Lock()

        def hold_slot():
            def _task():
                barrier.wait()  # tunggu sampai semua thread siap
                time.sleep(1.0)  # tahan semaphore
                return "done"

            try:
                r = bh.execute(_task)
                with lock:
                    results.append(("success", r))
            except BulkheadFullException:
                with lock:
                    results.append(("rejected", None))

        # 2 thread akan hold slot, 1 akan ditolak
        threads = [threading.Thread(target=hold_slot) for _ in range(3)]
        for t in threads:
            t.start()
        barrier.wait()  # release semua

        # Wait a bit for rejection to happen
        time.sleep(0.1)

        for t in threads:
            t.join(timeout=2.0)

        rejected = [r for r in results if r[0] == "rejected"]
        assert len(rejected) >= 1, "Setidaknya 1 request harus ditolak"

    def test_permit_released_after_execution(self):
        """Available permits kembali setelah eksekusi selesai."""
        bh = SemaphoreBulkhead("sema-permit", max_concurrent_calls=3)
        assert bh.available_permits == 3

        bh.execute(fast_task)
        assert bh.available_permits == 3  # kembali penuh setelah selesai

    def test_metrics_accuracy(self):
        """Metrics semaphore akurat."""
        bh = SemaphoreBulkhead("sema-metrics", max_concurrent_calls=5)

        for _ in range(3):
            bh.execute(fast_task)

        assert bh.metrics.total_accepted == 3
        assert bh.metrics.total_success == 3
        assert bh.metrics.total_rejected == 0

    def test_exception_propagation(self):
        """Exception dari task propagate ke caller."""
        bh = SemaphoreBulkhead("sema-exc", max_concurrent_calls=5)
        with pytest.raises(ValueError):
            bh.execute(failing_task)

        assert bh.metrics.total_failure == 1

    def test_as_decorator(self):
        """SemaphoreBulkhead bisa digunakan sebagai decorator."""
        bh = SemaphoreBulkhead("sema-dec", max_concurrent_calls=5)

        @bh
        def my_func(x):
            return x * 2

        assert my_func(21) == 42


# ─────────────────────────────────────────────
# Tests: BulkheadRegistry
# ─────────────────────────────────────────────

class TestBulkheadRegistry:

    def test_register_and_get(self):
        """Bisa register dan retrieve bulkhead dari registry."""
        registry = BulkheadRegistry()
        bh = ThreadPoolBulkhead("reg-test", max_concurrent_calls=5)
        registry.register(bh)

        retrieved = registry.get("reg-test")
        assert retrieved is bh
        bh.shutdown()

    def test_get_nonexistent_returns_none(self):
        """Get bulkhead yang tidak ada mengembalikan None."""
        registry = BulkheadRegistry()
        assert registry.get("does-not-exist") is None

    def test_get_or_create_creates_new(self):
        """get_or_create membuat bulkhead baru jika belum ada."""
        registry = BulkheadRegistry()
        bh = registry.get_or_create("new-bh", max_concurrent_calls=10)
        assert bh is not None
        assert bh.name == "new-bh"
        assert bh.max_concurrent_calls == 10
        bh.shutdown()

    def test_get_or_create_reuses_existing(self):
        """get_or_create mengembalikan bulkhead yang sama jika sudah ada."""
        registry = BulkheadRegistry()
        bh1 = registry.get_or_create("reuse-bh", max_concurrent_calls=5)
        bh2 = registry.get_or_create("reuse-bh", max_concurrent_calls=999)  # config berbeda!

        assert bh1 is bh2  # sama instance
        assert bh1.max_concurrent_calls == 5  # config pertama yang dipakai
        bh1.shutdown()

    def test_all_metrics(self):
        """all_metrics mengembalikan metrics dari semua bulkhead."""
        registry = BulkheadRegistry()
        bh1 = registry.get_or_create("m1", max_concurrent_calls=5)
        bh2 = registry.get_or_create("m2", max_concurrent_calls=5)

        all_m = registry.all_metrics()
        assert len(all_m) == 2
        names = {m.name for m in all_m}
        assert "m1" in names
        assert "m2" in names

        bh1.shutdown()
        bh2.shutdown()

    def test_get_or_create_semaphore_type(self):
        """get_or_create bisa membuat SemaphoreBulkhead."""
        registry = BulkheadRegistry()
        bh = registry.get_or_create("sema-reg", max_concurrent_calls=5, bulkhead_type="semaphore")
        assert isinstance(bh, SemaphoreBulkhead)


# ─────────────────────────────────────────────
# Tests: Decorator
# ─────────────────────────────────────────────

class TestBulkheadDecorator:

    def test_decorator_basic(self):
        """Decorator @bulkhead membungkus fungsi dengan benar."""
        @bulkhead("dec-basic", max_concurrent_calls=5)
        def my_service(val):
            return val + "_processed"

        result = my_service("data")
        assert result == "data_processed"

    def test_decorator_rejects_when_full(self):
        """Decorator menolak saat bulkhead penuh."""
        @bulkhead("dec-reject", max_concurrent_calls=1, max_wait_duration=0.1)
        def my_service():
            time.sleep(2.0)

        t = threading.Thread(target=my_service)
        t.start()
        time.sleep(0.05)

        with pytest.raises(BulkheadFullException):
            my_service()

        t.join(timeout=3.0)

    def test_decorator_preserves_function_name(self):
        """Decorator mempertahankan nama fungsi asli."""
        @bulkhead("dec-name", max_concurrent_calls=5)
        def my_important_function():
            pass

        assert my_important_function.__name__ == "my_important_function"


# ─────────────────────────────────────────────
# Tests: BulkheadMetrics
# ─────────────────────────────────────────────

class TestBulkheadMetrics:

    def test_initial_state(self):
        """State awal metrics adalah semua nol."""
        m = BulkheadMetrics("test")
        assert m.total_accepted == 0
        assert m.total_rejected == 0
        assert m.total_success == 0
        assert m.total_failure == 0
        assert m.total_calls == 0
        assert m.rejection_rate == 0.0
        assert m.success_rate == 0.0

    def test_success_rate_calculation(self):
        """Success rate dihitung dengan benar."""
        m = BulkheadMetrics("test-rate")
        m.record_accepted()
        m.record_accepted()
        m.record_accepted()
        m.record_success()
        m.record_success()
        m.record_failure()

        assert abs(m.success_rate - 66.67) < 0.1

    def test_rejection_rate_zero_division(self):
        """Rejection rate tidak crash jika total_calls = 0."""
        m = BulkheadMetrics("empty")
        assert m.rejection_rate == 0.0
        assert m.success_rate == 0.0

    def test_thread_safe_recording(self):
        """Metrics thread-safe — concurrent updates tidak menyebabkan race condition."""
        m = BulkheadMetrics("ts-test")
        threads = [threading.Thread(target=m.record_accepted) for _ in range(100)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert m.total_accepted == 100

    def test_summary_string(self):
        """summary() menghasilkan string yang informatif."""
        m = BulkheadMetrics("summary-test")
        m.record_accepted()
        m.record_success()
        m.record_rejected()

        s = m.summary()
        assert "summary-test" in s
        assert "Accepted: 1" in s or "1" in s


# ─────────────────────────────────────────────
# Tests: Concurrency & Edge Cases
# ─────────────────────────────────────────────

class TestConcurrencyEdgeCases:

    def test_concurrent_accepts_within_limit(self):
        """N concurrent requests dalam limit berjalan semua."""
        bh = ThreadPoolBulkhead("conc-ok", max_concurrent_calls=10)
        results = []
        lock = threading.Lock()

        def task(i):
            r = bh.execute(fast_task, f"result_{i}", delay=0.05)
            with lock:
                results.append(r)

        threads = [threading.Thread(target=task, args=(i,)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results) == 8
        bh.shutdown()

    def test_high_concurrency_all_within_limit(self):
        """100 requests concurrent, semua dalam limit 100 — semua harus diterima."""
        bh = ThreadPoolBulkhead("conc-high", max_concurrent_calls=100, max_wait_duration=5.0)
        success_count = [0]
        lock = threading.Lock()

        def task():
            r = bh.execute(fast_task, delay=0.01)
            with lock:
                success_count[0] += 1

        threads = [threading.Thread(target=task) for _ in range(100)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert success_count[0] == 100
        bh.shutdown()

    def test_submit_async_execution(self):
        """submit() mengeksekusi secara asinkron dan Future tersedia."""
        bh = ThreadPoolBulkhead("submit-test", max_concurrent_calls=5)
        future = bh.submit(fast_task, "async_result", delay=0.1)
        result = future.result(timeout=2.0)
        assert result == "async_result"
        bh.shutdown()

    def test_submit_rejected_when_full(self):
        """submit() juga membuang BulkheadFullException saat penuh."""
        bh = ThreadPoolBulkhead("submit-reject", max_concurrent_calls=1)

        # Isi pool
        bh.submit(slow_task, delay=2.0)
        time.sleep(0.05)

        with pytest.raises(BulkheadFullException):
            bh.submit(fast_task)

        bh.shutdown(wait=False)


# ─────────────────────────────────────────────
# Integration Test: E-Commerce Scenario
# ─────────────────────────────────────────────

class TestECommerceScenario:
    """Integration test mensimulasikan skenario e-commerce nyata."""

    def test_checkout_unaffected_by_slow_recommendation(self):
        """
        Skenario utama: Recommendation service lambat tidak memengaruhi Checkout.
        Ini adalah nilai proposisi utama Bulkhead Pattern.
        """
        checkout_bh = ThreadPoolBulkhead("integ-checkout", max_concurrent_calls=10, max_wait_duration=2.0)
        recommend_bh = ThreadPoolBulkhead("integ-recommend", max_concurrent_calls=2, max_wait_duration=0.2)

        checkout_times = []
        recommend_results = []
        lock = threading.Lock()

        def do_checkout():
            start = time.time()
            result = checkout_bh.execute(fast_task, "order_ok", delay=0.05)
            elapsed = time.time() - start
            with lock:
                checkout_times.append(elapsed)
            return result

        def do_slow_recommend():
            try:
                recommend_bh.execute(slow_task, delay=3.0)
                with lock:
                    recommend_results.append("slow_done")
            except BulkheadFullException:
                with lock:
                    recommend_results.append("rejected")

        # Mulai 2 slow recommendation threads (isi pool rekomendasi)
        rec_threads = [threading.Thread(target=do_slow_recommend) for _ in range(3)]
        for t in rec_threads:
            t.start()
        time.sleep(0.1)  # tunggu pool rekomendasi terisi

        # Sekarang lakukan 5 checkout — harus tetap cepat
        checkout_start = time.time()
        checkout_threads = [threading.Thread(target=do_checkout) for _ in range(5)]
        for t in checkout_threads:
            t.start()
        for t in checkout_threads:
            t.join(timeout=2.0)
        checkout_elapsed = time.time() - checkout_start

        # Checkout harus selesai dalam < 0.5 detik (bukan 3 detik!)
        assert checkout_elapsed < 0.5, (
            f"Checkout terlalu lambat ({checkout_elapsed:.2f}s) — "
            f"mungkin terpengaruh oleh recommendation yang lambat!"
        )
        assert len(checkout_times) == 5, "Semua 5 checkout harus berhasil"
        assert all(t < 0.3 for t in checkout_times), "Setiap checkout harus < 0.3s"

        for t in rec_threads:
            t.join(timeout=4.0)
        checkout_bh.shutdown()
        recommend_bh.shutdown()
