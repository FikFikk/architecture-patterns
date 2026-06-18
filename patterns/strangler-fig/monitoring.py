"""
Monitoring & Observability untuk Strangler Fig Pattern

Track metrics untuk migration progress dan system health.
"""

from prometheus_client import Counter, Histogram, Gauge, generate_latest
from functools import wraps
import time
import asyncio
from typing import Callable

# ==========================================
# Prometheus Metrics
# ==========================================

# Request counters
requests_legacy = Counter(
    'requests_legacy_total',
    'Total requests routed to legacy system',
    ['endpoint', 'method']
)

requests_new = Counter(
    'requests_new_total',
    'Total requests routed to new service',
    ['service', 'endpoint', 'method']
)

# Error tracking
migration_errors = Counter(
    'migration_errors_total',
    'Total migration-related errors',
    ['error_type', 'service']
)

dual_write_failures = Counter(
    'dual_write_failures_total',
    'Failed dual writes to legacy',
    ['service']
)

fallback_reads = Counter(
    'fallback_reads_total',
    'Reads that fell back to legacy',
    ['service']
)

# Response time tracking
response_time = Histogram(
    'response_time_seconds',
    'Response time in seconds',
    ['service', 'endpoint'],
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0]
)

# Migration progress
migration_progress = Gauge(
    'migration_progress_percentage',
    'Migration progress percentage',
    ['service']
)

traffic_split = Gauge(
    'traffic_split_percentage',
    'Percentage of traffic to new service',
    ['service']
)

# Data consistency
data_mismatches = Counter(
    'data_mismatches_total',
    'Data inconsistencies between legacy and new',
    ['service', 'field']
)

# ==========================================
# Decorators untuk Monitoring
# ==========================================

def track_request(service: str):
    """
    Decorator untuk track requests dan response time.
    
    Usage:
        @track_request("users")
        async def get_user(user_id: int):
            ...
    """
    def decorator(func: Callable):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            endpoint = func.__name__
            start_time = time.time()
            
            try:
                # Track request
                if service == "legacy":
                    requests_legacy.labels(
                        endpoint=endpoint,
                        method="GET"
                    ).inc()
                else:
                    requests_new.labels(
                        service=service,
                        endpoint=endpoint,
                        method="GET"
                    ).inc()
                
                # Execute function
                result = await func(*args, **kwargs)
                return result
                
            except Exception as e:
                migration_errors.labels(
                    error_type=type(e).__name__,
                    service=service
                ).inc()
                raise
                
            finally:
                # Track response time
                duration = time.time() - start_time
                response_time.labels(
                    service=service,
                    endpoint=endpoint
                ).observe(duration)
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            endpoint = func.__name__
            start_time = time.time()
            
            try:
                if service == "legacy":
                    requests_legacy.labels(
                        endpoint=endpoint,
                        method="GET"
                    ).inc()
                else:
                    requests_new.labels(
                        service=service,
                        endpoint=endpoint,
                        method="GET"
                    ).inc()
                
                result = func(*args, **kwargs)
                return result
                
            except Exception as e:
                migration_errors.labels(
                    error_type=type(e).__name__,
                    service=service
                ).inc()
                raise
                
            finally:
                duration = time.time() - start_time
                response_time.labels(
                    service=service,
                    endpoint=endpoint
                ).observe(duration)
        
        # Return appropriate wrapper based on function type
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator

# ==========================================
# Migration Tracking
# ==========================================

class MigrationTracker:
    """Track migration progress untuk each service"""
    
    def __init__(self):
        self.services = {}
    
    def update_progress(self, service: str, percentage: float):
        """Update migration progress (0-100)"""
        migration_progress.labels(service=service).set(percentage)
        self.services[service] = percentage
    
    def update_traffic_split(self, service: str, percentage: float):
        """Update traffic split percentage ke new service"""
        traffic_split.labels(service=service).set(percentage)
    
    def track_dual_write_failure(self, service: str):
        """Track dual write failure"""
        dual_write_failures.labels(service=service).inc()
    
    def track_fallback_read(self, service: str):
        """Track fallback read to legacy"""
        fallback_reads.labels(service=service).inc()
    
    def track_data_mismatch(self, service: str, field: str):
        """Track data inconsistency"""
        data_mismatches.labels(service=service, field=field).inc()
    
    def get_status(self) -> dict:
        """Get current migration status"""
        return {
            "services": self.services,
            "summary": {
                "total_services": len(self.services),
                "completed": sum(1 for p in self.services.values() if p >= 100),
                "in_progress": sum(1 for p in self.services.values() if 0 < p < 100),
                "not_started": sum(1 for p in self.services.values() if p == 0)
            }
        }

# Global tracker instance
tracker = MigrationTracker()

# ==========================================
# Shadow Mode Comparator
# ==========================================

class ShadowModeComparator:
    """
    Compare responses dari legacy vs new service di shadow mode.
    Berguna untuk detect regressions sebelum full cutover.
    """
    
    def __init__(self):
        self.comparison_counter = Counter(
            'shadow_comparisons_total',
            'Total shadow mode comparisons',
            ['service', 'result']
        )
    
    async def compare_responses(
        self,
        service: str,
        legacy_response: dict,
        new_response: dict,
        ignore_fields: list = None
    ) -> dict:
        """
        Compare responses dan track differences.
        
        Args:
            service: Service name
            legacy_response: Response dari legacy
            new_response: Response dari new service
            ignore_fields: Fields to ignore dalam comparison
        
        Returns:
            Comparison result dengan differences
        """
        ignore_fields = ignore_fields or []
        differences = []
        
        # Compare fields
        all_keys = set(legacy_response.keys()) | set(new_response.keys())
        
        for key in all_keys:
            if key in ignore_fields:
                continue
            
            legacy_value = legacy_response.get(key)
            new_value = new_response.get(key)
            
            if legacy_value != new_value:
                differences.append({
                    "field": key,
                    "legacy": legacy_value,
                    "new": new_value
                })
                
                # Track metric
                tracker.track_data_mismatch(service, key)
        
        # Track comparison result
        result = "match" if not differences else "mismatch"
        self.comparison_counter.labels(
            service=service,
            result=result
        ).inc()
        
        return {
            "match": not differences,
            "differences": differences,
            "legacy_response": legacy_response,
            "new_response": new_response
        }

comparator = ShadowModeComparator()

# ==========================================
# Usage Examples
# ==========================================

@track_request("users")
async def get_user_new(user_id: int):
    """Example: tracked function"""
    await asyncio.sleep(0.1)  # Simulate work
    return {"id": user_id, "name": "Alice"}

@track_request("legacy")
async def get_user_legacy(user_id: int):
    """Example: legacy function"""
    await asyncio.sleep(0.2)  # Legacy is slower
    return {"id": user_id, "full_name": "Alice"}

async def example_shadow_mode():
    """Example: shadow mode dengan comparison"""
    
    user_id = 123
    
    # Call both
    legacy_resp = await get_user_legacy(user_id)
    new_resp = await get_user_new(user_id)
    
    # Compare responses
    comparison = await comparator.compare_responses(
        service="users",
        legacy_response=legacy_resp,
        new_response=new_resp,
        ignore_fields=["created_at"]  # Ignore timestamp fields
    )
    
    if not comparison["match"]:
        print(f"Mismatch detected: {comparison['differences']}")
    
    # Always return legacy response in shadow mode
    return legacy_resp

def example_track_progress():
    """Example: track migration progress"""
    
    # Update progress for users service
    tracker.update_progress("users", 75.0)  # 75% migrated
    tracker.update_traffic_split("users", 50.0)  # 50% traffic to new
    
    # Update for orders service
    tracker.update_progress("orders", 25.0)
    tracker.update_traffic_split("orders", 10.0)  # 10% canary
    
    # Get status
    status = tracker.get_status()
    print(f"Migration status: {status}")

# ==========================================
# Metrics Endpoint (untuk Prometheus scraping)
# ==========================================

def get_metrics() -> bytes:
    """
    Get metrics dalam Prometheus format.
    
    Di production, expose ini via HTTP endpoint:
        GET /metrics
    """
    return generate_latest()

if __name__ == "__main__":
    # Example usage
    import asyncio
    
    async def main():
        print("=== Running monitoring examples ===\n")
        
        # Example 1: Track requests
        print("Example 1: Tracked requests")
        await get_user_new(123)
        await get_user_legacy(456)
        
        # Example 2: Shadow mode
        print("\nExample 2: Shadow mode comparison")
        await example_shadow_mode()
        
        # Example 3: Track progress
        print("\nExample 3: Migration progress")
        example_track_progress()
        
        # Print metrics
        print("\n=== Prometheus Metrics ===")
        print(get_metrics().decode())
    
    asyncio.run(main())
