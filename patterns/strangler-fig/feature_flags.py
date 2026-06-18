"""
Feature Flags untuk Strangler Fig Pattern

Mengontrol rollout bertahap dari legacy ke service baru.
"""

import os
from enum import Enum
from typing import Optional
import hashlib

class MigrationStage(Enum):
    """Stage migrasi dari legacy ke service baru"""
    LEGACY_ONLY = "legacy"           # Semua traffic ke legacy
    SHADOW_MODE = "shadow"           # Panggil keduanya, pakai legacy
    CANARY = "canary"                # Percentage traffic ke new
    NEW_PRIMARY = "new"              # New primary, legacy fallback
    NEW_ONLY = "new_only"            # 100% new, legacy retired

class FeatureFlags:
    """
    Feature flags untuk control migrasi per service.
    
    Di production, gunakan feature flag service seperti:
    - LaunchDarkly
    - Unleash
    - Split.io
    """
    
    def __init__(self):
        # Load dari environment variables
        self.users_service_stage = os.getenv(
            "USERS_SERVICE_STAGE",
            MigrationStage.LEGACY_ONLY.value
        )
        self.orders_service_stage = os.getenv(
            "ORDERS_SERVICE_STAGE",
            MigrationStage.LEGACY_ONLY.value
        )
        self.products_service_stage = os.getenv(
            "PRODUCTS_SERVICE_STAGE",
            MigrationStage.LEGACY_ONLY.value
        )
        
        # Canary percentage (0-100)
        self.canary_percentage = int(os.getenv("CANARY_PCT", "0"))
        
        # Canary users (whitelist untuk testing)
        canary_users_env = os.getenv("CANARY_USERS", "")
        self.canary_users = set(
            int(u) for u in canary_users_env.split(",") if u.strip()
        ) if canary_users_env else set()
    
    def should_use_new_service(
        self, 
        service: str, 
        user_id: Optional[int] = None
    ) -> bool:
        """
        Determine apakah request harus ke service baru atau legacy.
        
        Args:
            service: Service name ("users", "orders", etc)
            user_id: User ID untuk consistent hashing di canary mode
        
        Returns:
            True jika harus pakai service baru, False untuk legacy
        """
        stage = self._get_stage(service)
        
        # NEW_ONLY: semua ke new
        if stage == MigrationStage.NEW_ONLY.value:
            return True
        
        # NEW_PRIMARY: prefer new, fallback ke legacy jika error
        if stage == MigrationStage.NEW_PRIMARY.value:
            return True
        
        # CANARY: percentage-based rollout
        if stage == MigrationStage.CANARY.value:
            return self._is_canary_user(user_id)
        
        # SHADOW_MODE: panggil keduanya (handled di caller)
        # LEGACY_ONLY: semua ke legacy
        return False
    
    def is_shadow_mode(self, service: str) -> bool:
        """Check apakah service dalam shadow mode"""
        stage = self._get_stage(service)
        return stage == MigrationStage.SHADOW_MODE.value
    
    def is_dual_write_enabled(self, service: str) -> bool:
        """
        Check apakah dual-write masih diperlukan.
        Dual-write needed sampai NEW_ONLY stage.
        """
        stage = self._get_stage(service)
        return stage != MigrationStage.NEW_ONLY.value
    
    def is_fallback_read_enabled(self, service: str) -> bool:
        """
        Check apakah fallback read ke legacy masih enabled.
        Fallback needed sampai NEW_ONLY stage.
        """
        stage = self._get_stage(service)
        return stage != MigrationStage.NEW_ONLY.value
    
    def _get_stage(self, service: str) -> str:
        """Get migration stage untuk service tertentu"""
        stage_map = {
            "users": self.users_service_stage,
            "orders": self.orders_service_stage,
            "products": self.products_service_stage,
        }
        return stage_map.get(service, MigrationStage.LEGACY_ONLY.value)
    
    def _is_canary_user(self, user_id: Optional[int]) -> bool:
        """
        Determine apakah user masuk dalam canary group.
        
        Menggunakan consistent hashing untuk ensure user yang sama
        selalu dapat experience yang sama.
        """
        # Whitelist users always get new service
        if user_id in self.canary_users:
            return True
        
        # No user_id, use random percentage
        if user_id is None:
            import random
            return random.randint(0, 99) < self.canary_percentage
        
        # Consistent hashing based on user_id
        hash_input = f"canary-{user_id}".encode()
        hash_value = int(hashlib.md5(hash_input).hexdigest(), 16)
        bucket = hash_value % 100
        
        return bucket < self.canary_percentage

# ==========================================
# Global instance
# ==========================================

flags = FeatureFlags()

# ==========================================
# Usage Examples
# ==========================================

def example_usage():
    """Contoh penggunaan feature flags"""
    
    # Example 1: Simple routing decision
    user_id = 12345
    if flags.should_use_new_service("users", user_id):
        print("Route to new users service")
    else:
        print("Route to legacy monolith")
    
    # Example 2: Shadow mode - call both
    if flags.is_shadow_mode("orders"):
        print("Call both legacy and new, compare results")
    
    # Example 3: Dual write check
    if flags.is_dual_write_enabled("products"):
        print("Write to both databases")
    else:
        print("Write only to new database")

if __name__ == "__main__":
    example_usage()
