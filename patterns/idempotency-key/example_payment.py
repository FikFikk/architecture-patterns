import os
import time
import uuid
from typing import Dict, Any, Optional, Tuple

# Interface simulasi DB untuk persistence transaksi
class MockDatabase:
    def __init__(self):
        self.accounts = {
            "acc-1": {"balance": 1000.0, "name": "Budi"},
            "acc-2": {"balance": 500.0, "name": "Siti"},
        }
        self.transactions = {}

    def get_balance(self, account_id: str) -> float:
        if account_id not in self.accounts:
            raise ValueError(f"Account {account_id} tidak ditemukan.")
        return self.accounts[account_id]["balance"]

    def transfer(self, transfer_id: str, from_acc: str, to_acc: str, amount: float) -> Dict[str, Any]:
        # Cek jika transaksi transfer_id sudah pernah diproses di DB
        if transfer_id in self.transactions:
            return self.transactions[transfer_id]

        if from_acc not in self.accounts or to_acc not in self.accounts:
            raise ValueError("Salah satu rekening bank tidak terdaftar.")

        if self.accounts[from_acc]["balance"] < amount:
            raise ValueError("Saldo pengirim tidak mencukupi untuk melakukan transfer.")

        # Eksekusi pemindahan saldo secara atomic
        self.accounts[from_acc]["balance"] -= amount
        self.accounts[to_acc]["balance"] += amount
        
        tx = {
            "transfer_id": transfer_id,
            "from": from_acc,
            "to": to_acc,
            "amount": amount,
            "status": "SUCCESS",
            "timestamp": time.time()
        }
        self.transactions[transfer_id] = tx
        return tx

# Controller / Service layer yang diproteksi oleh IdempotencyManager
class PaymentService:
    def __init__(self, idempotency_manager, db: MockDatabase):
        self.idempotency = idempotency_manager
        self.db = db

    def process_payment(self, client_id: str, idempotency_key: str, from_acc: str, to_acc: str, amount: float) -> Tuple[Dict[str, Any], int]:
        """
        Memproses transaksi finansial dengan proteksi idempotency key.
        """
        if not idempotency_key:
            # Jika tidak ada key, proses normal tanpa caching/blocking idempotensi (tidak direkomendasikan untuk transaksi)
            tx = self.db.transfer(str(uuid.uuid4()), from_acc, to_acc, amount)
            return {"status": "success", "data": tx, "idempotent": False}, 200

        try:
            # 1. Coba dapatkan lock/cek cached response
            lock_acquired, cached_response, status_code = self.idempotency.try_lock(client_id, idempotency_key)
            
            if not lock_acquired:
                # Cache hit! Kembalikan hasil yang sudah pernah diperoleh
                return {
                    "status": "success", 
                    "data": cached_response, 
                    "idempotent": True,
                    "cached": True
                }, status_code

            # 2. Lock berhasil diperoleh (PROCESSING). Lakukan biz logic
            try:
                tx_result = self.db.transfer(idempotency_key, from_acc, to_acc, amount)
                response_body = {"status": "success", "data": tx_result}
                response_status = 200
                
                # 3. Simpan response & ubah status ke COMPLETED
                self.idempotency.save_response(client_id, idempotency_key, response_body, response_status)
                return response_body, response_status
                
            except Exception as biz_err:
                # 4. Jika logic gagal, bebaskan lock agar bisa di-retry dengan aman
                self.idempotency.release_lock(client_id, idempotency_key)
                return {"status": "failed", "error": str(biz_err)}, 400

        except Exception as e:
            # Handle error idempotency (e.g. key is processing, dll)
            return {"status": "error", "message": str(e)}, 409
