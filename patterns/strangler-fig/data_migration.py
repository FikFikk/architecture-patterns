"""
Data Migration Strategy untuk Strangler Fig Pattern

Implementasi dual-write dan batch migration untuk transisi data
dari legacy database ke database baru.
"""

import asyncio
from typing import Dict, List, Optional
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ==========================================
# Mock Database Connections
# ==========================================

class LegacyDatabase:
    """Simulasi legacy database"""
    
    def __init__(self):
        self.data = {
            1: {"id": 1, "full_name": "Alice Smith", "email": "alice@example.com"},
            2: {"id": 2, "full_name": "Bob Jones", "email": "bob@example.com"},
            3: {"id": 3, "full_name": "Charlie Brown", "email": "charlie@example.com"},
        }
    
    async def get(self, user_id: int) -> Optional[Dict]:
        """Get user from legacy DB"""
        await asyncio.sleep(0.1)  # Simulate DB latency
        return self.data.get(user_id)
    
    async def find(self, limit: int = 100, offset: int = 0, filter: Dict = None) -> List[Dict]:
        """Find users dengan pagination"""
        await asyncio.sleep(0.2)
        all_users = list(self.data.values())
        
        # Apply filter jika ada
        if filter:
            migrated = filter.get("migrated", None)
            if migrated is not None:
                all_users = [u for u in all_users if u.get("migrated", False) == migrated]
        
        return all_users[offset:offset+limit]
    
    async def update(self, user_id: int, data: Dict):
        """Update user di legacy DB"""
        await asyncio.sleep(0.1)
        if user_id in self.data:
            self.data[user_id].update(data)
    
    async def insert(self, data: Dict):
        """Insert user ke legacy DB"""
        await asyncio.sleep(0.1)
        user_id = data["id"]
        # Transform dari format baru ke legacy
        self.data[user_id] = {
            "id": data["id"],
            "full_name": data["name"],  # name → full_name
            "email": data["email"]
        }

class NewDatabase:
    """Simulasi new database"""
    
    def __init__(self):
        self.data = {}
    
    async def get(self, user_id: int) -> Optional[Dict]:
        """Get user from new DB"""
        await asyncio.sleep(0.05)  # Faster than legacy
        return self.data.get(user_id)
    
    async def insert(self, data: Dict):
        """Insert user ke new DB"""
        await asyncio.sleep(0.05)
        self.data[data["id"]] = data
    
    async def count(self) -> int:
        """Count total users"""
        return len(self.data)

# ==========================================
# Data Migration Service
# ==========================================

class DataMigrationService:
    """
    Service untuk handle data migration dari legacy ke new database.
    
    Strategy:
    1. Dual-write: Write ke kedua database during transition
    2. Lazy migration: Migrate data on-read
    3. Batch migration: Background job untuk migrate bulk data
    """
    
    def __init__(self):
        self.legacy_db = LegacyDatabase()
        self.new_db = NewDatabase()
        self.dual_write_enabled = True
        self.fallback_read_enabled = True
    
    async def write_user(self, user: Dict):
        """
        Write user dengan dual-write strategy.
        
        Primary write ke new DB, secondary write ke legacy
        untuk backward compatibility.
        """
        # Write to new DB (source of truth)
        try:
            await self.new_db.insert(user)
            logger.info(f"Written user {user['id']} to new DB")
        except Exception as e:
            logger.error(f"Failed to write to new DB: {e}")
            raise  # Fail fast jika new DB error
        
        # Dual write to legacy (best effort)
        if self.dual_write_enabled:
            try:
                await self.legacy_db.insert(user)
                logger.info(f"Written user {user['id']} to legacy DB")
            except Exception as e:
                # Log but don't fail - new DB is source of truth
                logger.warning(f"Dual write to legacy failed: {e}")
    
    async def read_user(self, user_id: int) -> Optional[Dict]:
        """
        Read user dengan fallback strategy.
        
        1. Try new DB first
        2. Fallback ke legacy jika not found
        3. Lazy migrate jika found di legacy
        """
        # Try new DB first
        user = await self.new_db.get(user_id)
        
        if user:
            logger.info(f"User {user_id} found in new DB")
            return user
        
        # Fallback ke legacy jika enabled
        if self.fallback_read_enabled:
            logger.info(f"User {user_id} not in new DB, checking legacy")
            legacy_user = await self.legacy_db.get(user_id)
            
            if legacy_user:
                # Transform dan migrate
                migrated_user = self._transform_from_legacy(legacy_user)
                
                # Lazy migration: save to new DB
                await self.new_db.insert(migrated_user)
                logger.info(f"Lazy migrated user {user_id}")
                
                # Mark as migrated in legacy (optional)
                await self.legacy_db.update(user_id, {"migrated": True})
                
                return migrated_user
        
        return None
    
    def _transform_from_legacy(self, legacy_user: Dict) -> Dict:
        """Transform dari legacy format ke new format"""
        return {
            "id": legacy_user["id"],
            "name": legacy_user["full_name"],  # full_name → name
            "email": legacy_user["email"],
            "status": "active",  # New field
            "migrated_at": datetime.utcnow().isoformat()
        }
    
    async def batch_migrate(self, batch_size: int = 100, delay: float = 1.0):
        """
        Batch migration untuk migrate data dalam background.
        
        Args:
            batch_size: Jumlah records per batch
            delay: Delay antar batch untuk rate limiting
        """
        offset = 0
        total_migrated = 0
        
        logger.info("Starting batch migration...")
        
        while True:
            # Fetch batch dari legacy (only non-migrated)
            users = await self.legacy_db.find(
                limit=batch_size,
                offset=offset,
                filter={"migrated": False}
            )
            
            if not users:
                logger.info("No more users to migrate")
                break
            
            # Migrate each user
            for legacy_user in users:
                try:
                    # Transform
                    new_user = self._transform_from_legacy(legacy_user)
                    
                    # Insert to new DB
                    await self.new_db.insert(new_user)
                    
                    # Mark as migrated in legacy
                    await self.legacy_db.update(
                        legacy_user["id"],
                        {"migrated": True}
                    )
                    
                    total_migrated += 1
                    logger.info(f"Migrated user {legacy_user['id']}")
                    
                except Exception as e:
                    logger.error(f"Failed to migrate user {legacy_user['id']}: {e}")
                    # Continue dengan user berikutnya
            
            offset += batch_size
            
            # Rate limiting
            await asyncio.sleep(delay)
            
            logger.info(f"Batch complete. Total migrated: {total_migrated}")
        
        logger.info(f"Batch migration complete. Total: {total_migrated} users")
        return total_migrated
    
    async def verify_migration(self) -> Dict:
        """
        Verify migration completeness dengan compare data.
        
        Returns:
            Dict dengan migration statistics
        """
        logger.info("Verifying migration...")
        
        # Count users in both DBs
        new_count = await self.new_db.count()
        
        # Sample check: verify beberapa users
        sample_ids = [1, 2, 3]
        mismatches = []
        
        for user_id in sample_ids:
            legacy_user = await self.legacy_db.get(user_id)
            new_user = await self.new_db.get(user_id)
            
            if legacy_user and not new_user:
                mismatches.append({
                    "user_id": user_id,
                    "issue": "missing_in_new_db"
                })
            elif legacy_user and new_user:
                # Verify data consistency
                if legacy_user["email"] != new_user["email"]:
                    mismatches.append({
                        "user_id": user_id,
                        "issue": "data_mismatch",
                        "field": "email"
                    })
        
        result = {
            "new_db_count": new_count,
            "mismatches": mismatches,
            "status": "complete" if not mismatches else "inconsistent"
        }
        
        logger.info(f"Verification result: {result}")
        return result

# ==========================================
# Usage Example
# ==========================================

async def main():
    """Example usage of data migration service"""
    
    service = DataMigrationService()
    
    # Example 1: Write dengan dual-write
    print("\n=== Example 1: Dual Write ===")
    new_user = {
        "id": 100,
        "name": "New User",
        "email": "newuser@example.com",
        "status": "active"
    }
    await service.write_user(new_user)
    
    # Example 2: Read dengan lazy migration
    print("\n=== Example 2: Lazy Migration on Read ===")
    user = await service.read_user(1)
    print(f"User: {user}")
    
    # Example 3: Batch migration
    print("\n=== Example 3: Batch Migration ===")
    total = await service.batch_migrate(batch_size=10, delay=0.5)
    print(f"Total migrated: {total}")
    
    # Example 4: Verify migration
    print("\n=== Example 4: Verify Migration ===")
    verification = await service.verify_migration()
    print(f"Verification: {verification}")

if __name__ == "__main__":
    asyncio.run(main())
