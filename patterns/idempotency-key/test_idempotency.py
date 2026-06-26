import pytest
import time
import uuid
import threading
from unittest.mock import MagicMock
import redis
from idempotency import IdempotencyManager, IdempotencyError
from example_payment import MockDatabase, PaymentService

class TestIdempotencyKeyPattern:
    @pytest.fixture(autouse=True)
    def setup_redis(self):
        """Fixture untuk in-memory / mock Redis client."""
        # Kita gunakan real Redis jika available, jika tidak fall back ke mock
        try:
            self.redis_client = redis.Redis(host="localhost", port=6379, db=0, socket_timeout=1)
            self.redis_client.ping()
            # Bersihkan test data
            self.redis_client.flushdb()
        except Exception:
            # Fallback ke mock Redis sederhana untuk unit testing
            class MockRedis:
                def __init__(self):
                    self.store = {}
                    
                def get(self, key):
                    return self.store.get(key)
                    
                def setex(self, key, expiry, value):
                    self.store[key] = value
                    
                def delete(self, key):
                    if key in self.store:
                        del self.store[key]
                        
                def register_script(self, script):
                    # Mocking script Lua execution
                    def run_script(keys, args):
                        key = keys[0]
                        now = float(args[0])
                        expiry = int(args[1])
                        
                        current_val = self.get(key)
                        if not current_val:
                            import json
                            initial = json.dumps({"status": "PROCESSING", "response_body": "", "response_status": 0, "created_at": now})
                            self.setex(key, expiry, initial)
                            return [1, None, None]
                        else:
                            import json
                            data = json.loads(current_val)
                            if data["status"] == "PROCESSING":
                                return [0, "PROCESSING", None]
                            elif data["status"] == "COMPLETED":
                                return [0, data["response_body"], data["response_status"]]
                        return [0, None, None]
                    return run_script
                    
                def flushdb(self):
                    self.store.clear()
            self.redis_client = MockRedis()

    def test_successful_first_request(self):
        """Memastikan request pertama berhasil memperoleh lock dan statusnya lengkap disave."""
        db = MockDatabase()
        manager = IdempotencyManager(self.redis_client)
        payment_service = PaymentService(manager, db)
        
        client_id = "client-99"
        idempotency_key = str(uuid.uuid4())
        
        response, status = payment_service.process_payment(client_id, idempotency_key, "acc-1", "acc-2", 100.0)
        
        assert status == 200
        assert response["status"] == "success"
        assert db.get_balance("acc-1") == 900.0
        assert db.get_balance("acc-2") == 600.0
        
        # Skenario: panggil ulang dengan key yg sama (replay request)
        response2, status2 = payment_service.process_payment(client_id, idempotency_key, "acc-1", "acc-2", 100.0)
        
        assert status2 == 200
        # Harus terdeteksi cached/idempotent
        assert response2["data"]["status"] == "success"
        assert response2["cached"] is True
        
        # Saldo tidak boleh berkurang lagi karena request ter-idempotency
        assert db.get_balance("acc-1") == 900.0
        assert db.get_balance("acc-2") == 600.0

    def test_payment_failure_releases_lock(self):
        """Memastikan jika bisnis logic gagal (e.g. saldo kurang), lock dilepaskan sehingga client bisa retry lagi."""
        db = MockDatabase()
        manager = IdempotencyManager(self.redis_client)
        payment_service = PaymentService(manager, db)
        
        client_id = "client-99"
        idempotency_key = str(uuid.uuid4())
        
        # Coba transfer melebihi limit saldo (harus gagal)
        response, status = payment_service.process_payment(client_id, idempotency_key, "acc-1", "acc-2", 5000.0)
        
        assert status == 400
        assert response["status"] == "failed"
        
        # Karena lock sudah dilepas, kita bisa panggil request ulang berkali-kali menggunakan key yang sama
        # (Misal setelah user topup saldo)
        db.accounts["acc-1"]["balance"] = 10000.0 # topup
        response2, status2 = payment_service.process_payment(client_id, idempotency_key, "acc-1", "acc-2", 5000.0)
        
        assert status2 == 200
        assert response2["status"] == "success"
        assert db.get_balance("acc-1") == 5000.0

    def test_concurrent_request_blocking(self):
        """Memastikan dua request concurrent dengan key yang sama menolak pemrosesan ganda."""
        db = MockDatabase()
        manager = IdempotencyManager(self.redis_client)
        payment_service = PaymentService(manager, db)
        
        client_id = "client-cc"
        idempotency_key = "idemp-cc-123"
        
        # Simulasikan proses awal sedang berjalan (PROCESSING)
        manager.try_lock(client_id, idempotency_key)
        
        # Request kedua masuk dengan key yang sama sementara pemrosesan pertama belum selesai
        response, status = payment_service.process_payment(client_id, idempotency_key, "acc-1", "acc-2", 100.0)
        
        assert status == 409
        assert "Request serupa sedang dalam proses" in response["message"]
