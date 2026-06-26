import uuid
import time
import json
import logging
from typing import Optional, Dict, Any, Tuple
import redis

# Tipe data data class untuk menyimpan request yang di-cache
from dataclasses import dataclass

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("idempotency")

@dataclass
class IdempotencyRecord:
    status: str            # "PROCESSING" atau "COMPLETED"
    response_body: str     # JSON string cache response
    response_status: int   # HTTP status code
    created_at: float

class IdempotencyError(Exception):
    """Exception untuk masalah idempotensi, e.g., dual-processing."""
    pass

class IdempotencyManager:
    """
    IdempotencyManager bertanggung jawab untuk mengelola siklus hidup kunci idempotensi (Idempotency Key).
    Mendukung penyimpanan berbasis Redis dengan mekanisme locking / state atomic.
    """
    def __init__(self, redis_client: redis.Redis, expiry_seconds: int = 86400):
        self.redis = redis_client
        self.expiry_seconds = expiry_seconds

    def _get_key(self, client_id: str, idempotency_key: str) -> str:
        return f"idempotency:{client_id}:{idempotency_key}"

    def try_lock(self, client_id: str, idempotency_key: str) -> Tuple[bool, Optional[Dict[str, Any]], Optional[int]]:
        """
        Mencoba mengunci request berdasarkan Idempotency Key secara atomik.
        
        Returns:
            - lock_acquired: bool (True jika kita berhasil mengunci untuk mulai proses, atau False jika sudah ada request yang jalan/selesai)
            - cached_response: Optional[dict] (Response yang di-cache jika statusnya "COMPLETED")
            - cached_status_code: Optional[int] (Status code yang di-cache)
        """
        redis_key = self._get_key(client_id, idempotency_key)
        
        # Gunakan MSETNX / transaksi atau Lua script untuk menjamin operasi atomik.
        # Kita buat hash/string status. Menggunakan Redis transaction (watch/multi) atau LUA script untuk memproses lock.
        # Format di Redis value: JSON string:
        # { "status": "PROCESSING", "response_body": "", "response_status": 0, "created_at": time.time() }
        
        lua_lock_script = """
        local key = KEYS[1]
        local current_val = redis.call('GET', key)
        if not current_val then
            -- Kunci belum ada, set status ke PROCESSING dan batasi waktu expire
            local initial_val = cjson.encode({status = "PROCESSING", response_body = "", response_status = 0, created_at = ARGV[1]})
            redis.call('SET', key, initial_val, 'EX', tonumber(ARGV[2]))
            return {1, nil, nil}
        else
            -- Kunci sudah ada, decode data
            local data = cjson.decode(current_val)
            if data.status == "PROCESSING" then
                -- Sedang diproses oleh request concurrent lain
                return {0, "PROCESSING", nil}
            elseif data.status == "COMPLETED" then
                -- Sudah selesai diproses sebelumnya, kembalikan response yang di-cache
                return {0, data.response_body, data.response_status}
            end
        end
        """
        
        now = time.time()
        result = self.redis.register_script(lua_lock_script)(keys=[redis_key], args=[now, self.expiry_seconds])
        
        lock_acquired = result[0] == 1
        
        if lock_acquired:
            return True, None, None
        
        # Jika lock tidak berhasil diperoleh
        status_or_body = result[1]
        status_code = result[2]
        
        if status_or_body == "PROCESSING":
            raise IdempotencyError("Request serupa sedang dalam proses. Silakan coba sesaat lagi.")
        
        # COMPLETED: status_or_body berisi response body cached
        response_data = json.loads(status_or_body) if status_or_body else None
        return False, response_data, status_code

    def save_response(self, client_id: str, idempotency_key: str, response_body: Dict[str, Any], status_code: int):
        """
        Menyimpan hasil response aplikasi ke dalam key idempotensi yang bersangkutan,
        dan ubah statusnya menjadi "COMPLETED".
        """
        redis_key = self._get_key(client_id, idempotency_key)
        logger.info(f"Menyimpan response ter-idempotensi untuk key: {redis_key}")
        
        data = {
            "status": "COMPLETED",
            "response_body": json.dumps(response_body),
            "response_status": status_code,
            "created_at": time.time()
        }
        
        # Overwrite value dengan payload lengkap dan set TTL
        self.redis.setex(redis_key, self.expiry_seconds, json.dumps(data))

    def release_lock(self, client_id: str, idempotency_key: str):
        """
        Menghapus lock jika proses di dalam handler/controller gagal sebelum menyimpan response,
        agar client bisa melakukan retry untuk request tersebut.
        """
        redis_key = self._get_key(client_id, idempotency_key)
        logger.info(f"Membebaskan lock idempotensi karena kegagalan proses: {redis_key}")
        self.redis.delete(redis_key)
