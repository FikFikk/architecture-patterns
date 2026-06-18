"""
Strangler Fig Pattern - Example Service Implementation

Contoh implementasi service baru yang menggantikan fitur di legacy monolith.
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, EmailStr
from typing import Optional, List
import httpx
import asyncio

app = FastAPI(title="Users Service", version="2.0")

# ==========================================
# Models
# ==========================================

class User(BaseModel):
    id: int
    name: str
    email: EmailStr
    status: str = "active"

class CreateUserRequest(BaseModel):
    name: str
    email: EmailStr

# ==========================================
# Mock Database (gunakan PostgreSQL di production)
# ==========================================

users_db = {
    1: {"id": 1, "name": "Alice", "email": "alice@example.com", "status": "active"},
    2: {"id": 2, "name": "Bob", "email": "bob@example.com", "status": "active"},
}

# ==========================================
# Configuration
# ==========================================

LEGACY_SERVICE_URL = "http://legacy-monolith:8080"
ENABLE_DUAL_WRITE = True  # Set False setelah migrasi selesai
ENABLE_FALLBACK_READ = True  # Set False setelah semua data dimigrate

# ==========================================
# Service Implementation
# ==========================================

@app.get("/health")
async def health_check():
    """Health check endpoint untuk load balancer"""
    return {"status": "healthy", "service": "users-service-v2"}

@app.get("/api/v2/users/{user_id}", response_model=User)
async def get_user(user_id: int):
    """
    Get user by ID dengan fallback ke legacy system.
    
    Strategy:
    1. Cek di database baru
    2. Jika tidak ada, fallback ke legacy
    3. Jika ada di legacy, migrate ke database baru (lazy migration)
    """
    # Try new database first
    user = users_db.get(user_id)
    
    if user:
        return user
    
    # Fallback ke legacy jika enabled
    if ENABLE_FALLBACK_READ:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(
                    f"{LEGACY_SERVICE_URL}/users/{user_id}"
                )
                
                if response.status_code == 200:
                    legacy_user = response.json()
                    
                    # Transform dari format legacy ke format baru
                    transformed_user = {
                        "id": legacy_user["id"],
                        "name": legacy_user["full_name"],  # Field name berubah
                        "email": legacy_user["email"],
                        "status": "active"  # Field baru
                    }
                    
                    # Lazy migration: simpan ke database baru
                    users_db[user_id] = transformed_user
                    
                    return transformed_user
        except httpx.TimeoutException:
            raise HTTPException(status_code=504, detail="Legacy service timeout")
        except Exception as e:
            # Log error tapi jangan expose detail
            print(f"Error fetching from legacy: {e}")
    
    raise HTTPException(status_code=404, detail="User not found")

@app.get("/api/v2/users", response_model=List[User])
async def list_users(limit: int = 100, offset: int = 0):
    """List users dengan pagination"""
    all_users = list(users_db.values())
    return all_users[offset:offset+limit]

@app.post("/api/v2/users", response_model=User, status_code=201)
async def create_user(request: CreateUserRequest):
    """
    Create user dengan dual-write ke legacy system.
    
    Strategy:
    1. Write ke database baru (source of truth)
    2. Async write ke legacy untuk backward compatibility
    3. Jika legacy write gagal, log tapi jangan fail request
    """
    # Generate ID (gunakan DB sequence di production)
    new_id = max(users_db.keys(), default=0) + 1
    
    new_user = {
        "id": new_id,
        "name": request.name,
        "email": request.email,
        "status": "active"
    }
    
    # Write to new database (primary)
    users_db[new_id] = new_user
    
    # Dual write ke legacy jika enabled
    if ENABLE_DUAL_WRITE:
        asyncio.create_task(
            write_to_legacy_async(new_user)
        )
    
    return new_user

@app.put("/api/v2/users/{user_id}", response_model=User)
async def update_user(user_id: int, request: CreateUserRequest):
    """Update user dengan dual-write"""
    if user_id not in users_db:
        raise HTTPException(status_code=404, detail="User not found")
    
    updated_user = {
        "id": user_id,
        "name": request.name,
        "email": request.email,
        "status": users_db[user_id]["status"]  # Preserve status
    }
    
    users_db[user_id] = updated_user
    
    # Dual write ke legacy
    if ENABLE_DUAL_WRITE:
        asyncio.create_task(
            write_to_legacy_async(updated_user)
        )
    
    return updated_user

@app.delete("/api/v2/users/{user_id}", status_code=204)
async def delete_user(user_id: int):
    """Soft delete user"""
    if user_id not in users_db:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Soft delete: set status instead of actual delete
    users_db[user_id]["status"] = "deleted"
    
    # Dual write ke legacy
    if ENABLE_DUAL_WRITE:
        asyncio.create_task(
            soft_delete_legacy_async(user_id)
        )
    
    return None

# ==========================================
# Helper Functions
# ==========================================

async def write_to_legacy_async(user: dict):
    """
    Async write ke legacy system.
    Jika gagal, log tapi jangan throw exception.
    """
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            # Transform ke format legacy
            legacy_format = {
                "id": user["id"],
                "full_name": user["name"],  # Field name berbeda
                "email": user["email"]
            }
            
            await client.post(
                f"{LEGACY_SERVICE_URL}/users",
                json=legacy_format
            )
            print(f"Successfully wrote user {user['id']} to legacy")
    except Exception as e:
        # Log tapi jangan fail - new DB adalah source of truth
        print(f"Failed to write to legacy: {e}")
        # Di production: send to monitoring/alerting

async def soft_delete_legacy_async(user_id: int):
    """Async soft delete di legacy system"""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.put(
                f"{LEGACY_SERVICE_URL}/users/{user_id}/deactivate"
            )
            print(f"Successfully deactivated user {user_id} in legacy")
    except Exception as e:
        print(f"Failed to deactivate in legacy: {e}")

# ==========================================
# Migration Utilities
# ==========================================

@app.post("/admin/migrate-user/{user_id}")
async def migrate_single_user(user_id: int):
    """
    Admin endpoint untuk force migrate satu user dari legacy.
    Berguna untuk testing atau selective migration.
    """
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                f"{LEGACY_SERVICE_URL}/users/{user_id}"
            )
            
            if response.status_code == 200:
                legacy_user = response.json()
                
                transformed_user = {
                    "id": legacy_user["id"],
                    "name": legacy_user["full_name"],
                    "email": legacy_user["email"],
                    "status": "active"
                }
                
                users_db[user_id] = transformed_user
                
                return {
                    "status": "migrated",
                    "user_id": user_id,
                    "user": transformed_user
                }
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Migration failed: {str(e)}"
        )
    
    raise HTTPException(status_code=404, detail="User not found in legacy")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8081)
