"""
Test untuk Strangler Fig Pattern Implementation

Test scenarios untuk verify migration behavior.
"""

import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
from feature_flags import FeatureFlags, MigrationStage
from data_migration import DataMigrationService

# ==========================================
# Feature Flags Tests
# ==========================================

class TestFeatureFlags:
    """Test feature flag behavior"""
    
    def test_legacy_only_stage(self):
        """Test LEGACY_ONLY stage routes all traffic to legacy"""
        flags = FeatureFlags()
        flags.users_service_stage = MigrationStage.LEGACY_ONLY.value
        
        # Semua user harus ke legacy
        assert flags.should_use_new_service("users", user_id=1) == False
        assert flags.should_use_new_service("users", user_id=100) == False
    
    def test_new_only_stage(self):
        """Test NEW_ONLY stage routes all traffic to new service"""
        flags = FeatureFlags()
        flags.users_service_stage = MigrationStage.NEW_ONLY.value
        
        # Semua user harus ke new service
        assert flags.should_use_new_service("users", user_id=1) == True
        assert flags.should_use_new_service("users", user_id=100) == True
    
    def test_canary_percentage(self):
        """Test canary deployment dengan percentage"""
        flags = FeatureFlags()
        flags.users_service_stage = MigrationStage.CANARY.value
        flags.canary_percentage = 50
        
        # Test dengan sample users
        results = []
        for user_id in range(100):
            results.append(flags.should_use_new_service("users", user_id))
        
        # Approximately 50% harus ke new service
        new_service_count = sum(results)
        assert 30 < new_service_count < 70  # Allow some variance
    
    def test_canary_whitelist(self):
        """Test canary whitelist users"""
        flags = FeatureFlags()
        flags.users_service_stage = MigrationStage.CANARY.value
        flags.canary_percentage = 0  # 0% rollout
        flags.canary_users = {1, 2, 3}  # But whitelist these users
        
        # Whitelisted users harus ke new service
        assert flags.should_use_new_service("users", user_id=1) == True
        assert flags.should_use_new_service("users", user_id=2) == True
        
        # Non-whitelisted users harus ke legacy
        assert flags.should_use_new_service("users", user_id=999) == False
    
    def test_shadow_mode_detection(self):
        """Test shadow mode detection"""
        flags = FeatureFlags()
        flags.users_service_stage = MigrationStage.SHADOW_MODE.value
        
        assert flags.is_shadow_mode("users") == True
        assert flags.should_use_new_service("users") == False  # Use legacy in shadow
    
    def test_dual_write_control(self):
        """Test dual write enable/disable based on stage"""
        flags = FeatureFlags()
        
        # Dual write enabled until NEW_ONLY
        flags.users_service_stage = MigrationStage.CANARY.value
        assert flags.is_dual_write_enabled("users") == True
        
        flags.users_service_stage = MigrationStage.NEW_PRIMARY.value
        assert flags.is_dual_write_enabled("users") == True
        
        # Disabled at NEW_ONLY
        flags.users_service_stage = MigrationStage.NEW_ONLY.value
        assert flags.is_dual_write_enabled("users") == False

# ==========================================
# Data Migration Tests
# ==========================================

@pytest.mark.asyncio
class TestDataMigration:
    """Test data migration scenarios"""
    
    async def test_dual_write_success(self):
        """Test successful dual write to both databases"""
        service = DataMigrationService()
        
        user = {
            "id": 100,
            "name": "Test User",
            "email": "test@example.com",
            "status": "active"
        }
        
        await service.write_user(user)
        
        # Verify written to new DB
        new_user = await service.new_db.get(100)
        assert new_user is not None
        assert new_user["name"] == "Test User"
        
        # Verify written to legacy DB (with transformation)
        legacy_user = await service.legacy_db.get(100)
        assert legacy_user is not None
        assert legacy_user["full_name"] == "Test User"  # Transformed field
    
    async def test_lazy_migration_on_read(self):
        """Test lazy migration when reading from legacy"""
        service = DataMigrationService()
        
        # User exists only in legacy
        legacy_user_id = 1
        
        # Read should trigger lazy migration
        user = await service.read_user(legacy_user_id)
        
        assert user is not None
        assert user["name"] == "Alice Smith"
        
        # Verify now in new DB
        new_user = await service.new_db.get(legacy_user_id)
        assert new_user is not None
    
    async def test_fallback_to_legacy(self):
        """Test fallback to legacy when not in new DB"""
        service = DataMigrationService()
        service.fallback_read_enabled = True
        
        # User not in new DB, should fallback to legacy
        user = await service.read_user(2)
        
        assert user is not None
        assert "name" in user
    
    async def test_no_fallback_when_disabled(self):
        """Test no fallback when disabled"""
        service = DataMigrationService()
        service.fallback_read_enabled = False
        
        # User not in new DB, should return None
        user = await service.read_user(999)
        
        assert user is None
    
    async def test_batch_migration(self):
        """Test batch migration process"""
        service = DataMigrationService()
        
        # Run batch migration
        total = await service.batch_migrate(batch_size=10, delay=0.1)
        
        # Verify users migrated
        assert total > 0
        
        # Check new DB has data
        count = await service.new_db.count()
        assert count == total
    
    async def test_dual_write_legacy_failure_resilience(self):
        """Test system continues when legacy write fails"""
        service = DataMigrationService()
        
        # Mock legacy DB to fail
        original_insert = service.legacy_db.insert
        service.legacy_db.insert = AsyncMock(side_effect=Exception("Legacy DB down"))
        
        user = {
            "id": 200,
            "name": "Test User",
            "email": "test@example.com",
            "status": "active"
        }
        
        # Should not raise exception
        await service.write_user(user)
        
        # Verify written to new DB (source of truth)
        new_user = await service.new_db.get(200)
        assert new_user is not None
        
        # Restore
        service.legacy_db.insert = original_insert

# ==========================================
# Integration Tests
# ==========================================

@pytest.mark.asyncio
class TestIntegration:
    """Integration tests untuk full migration flow"""
    
    async def test_migration_workflow(self):
        """
        Test complete migration workflow:
        1. Start with LEGACY_ONLY
        2. Move to SHADOW_MODE
        3. Move to CANARY
        4. Move to NEW_PRIMARY
        5. Move to NEW_ONLY
        """
        flags = FeatureFlags()
        service = DataMigrationService()
        
        # Stage 1: LEGACY_ONLY
        flags.users_service_stage = MigrationStage.LEGACY_ONLY.value
        assert flags.should_use_new_service("users", 1) == False
        
        # Stage 2: SHADOW_MODE - call both, use legacy
        flags.users_service_stage = MigrationStage.SHADOW_MODE.value
        assert flags.is_shadow_mode("users") == True
        
        # Stage 3: CANARY - gradual rollout
        flags.users_service_stage = MigrationStage.CANARY.value
        flags.canary_percentage = 25
        
        # Stage 4: NEW_PRIMARY - prefer new, fallback to legacy
        flags.users_service_stage = MigrationStage.NEW_PRIMARY.value
        assert flags.should_use_new_service("users", 1) == True
        assert flags.is_fallback_read_enabled("users") == True
        
        # Stage 5: NEW_ONLY - legacy retired
        flags.users_service_stage = MigrationStage.NEW_ONLY.value
        assert flags.should_use_new_service("users", 1) == True
        assert flags.is_dual_write_enabled("users") == False
        assert flags.is_fallback_read_enabled("users") == False

# ==========================================
# Run Tests
# ==========================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
