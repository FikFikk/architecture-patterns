"""
Snapshot Implementation untuk Performance Optimization

Snapshot mengurangi jumlah events yang perlu di-replay untuk load aggregate.
Best practice: snapshot setiap N events (misal 100 events).
"""

from typing import Optional, Dict, Any
from datetime import datetime
from event_store import event_store, snapshot_store
from example_order import OrderAggregate
from example_bank import BankAccountAggregate


class SnapshotManager:
    """
    Manager untuk snapshot lifecycle.
    
    Responsibilities:
    - Decide when to create snapshot
    - Load aggregate with snapshot optimization
    - Manage snapshot retention
    """
    
    def __init__(self, snapshot_threshold: int = 100):
        """
        Args:
            snapshot_threshold: Buat snapshot setiap N events
        """
        self.snapshot_threshold = snapshot_threshold
    
    def should_snapshot(self, aggregate_id: str) -> bool:
        """Check apakah aggregate perlu di-snapshot"""
        version = event_store.get_current_version(aggregate_id)
        
        # Snapshot jika sudah mencapai threshold
        return version > 0 and version % self.snapshot_threshold == 0
    
    def save_order_snapshot(self, order: OrderAggregate):
        """Save snapshot untuk Order aggregate"""
        state = {
            "order_id": order.order_id,
            "customer_id": order.customer_id,
            "items": [item.to_dict() for item in order.items],
            "total": order.total,
            "status": order.status.value,
            "payment_method": order.payment_method,
            "shipping_address": order.shipping_address,
            "tracking_number": order.tracking_number
        }
        
        snapshot_store.save_snapshot(
            aggregate_id=order.order_id,
            state=state,
            version=order.version
        )
        
        print(f"✓ Snapshot saved for {order.order_id} at version {order.version}")
    
    def load_order_with_snapshot(self, order_id: str) -> Optional[OrderAggregate]:
        """
        Load Order aggregate dengan snapshot optimization.
        
        Process:
        1. Coba load snapshot
        2. Jika ada, load dari snapshot + replay events setelah snapshot
        3. Jika tidak ada, replay semua events
        """
        # Try snapshot
        snapshot = snapshot_store.get_snapshot(order_id)
        
        if snapshot:
            state, snapshot_version = snapshot
            print(f"✓ Loaded snapshot at version {snapshot_version}")
            
            # Rebuild dari snapshot
            order = OrderAggregate(order_id)
            order.customer_id = state["customer_id"]
            order.total = state["total"]
            order.status = state["status"]
            order.payment_method = state.get("payment_method")
            order.shipping_address = state.get("shipping_address")
            order.tracking_number = state.get("tracking_number")
            order.version = snapshot_version
            
            # Replay events setelah snapshot
            events_after = event_store.get_events(order_id, from_version=snapshot_version)
            print(f"✓ Replaying {len(events_after)} events after snapshot")
            
            for event in events_after:
                if event.event_type == "PaymentReceived":
                    order._apply_payment_received(event)
                elif event.event_type == "OrderShipped":
                    order._apply_order_shipped(event)
                elif event.event_type == "OrderDelivered":
                    order._apply_order_delivered(event)
                elif event.event_type == "OrderCancelled":
                    order._apply_order_cancelled(event)
            
            return order
        else:
            # No snapshot, load dari history biasa
            print(f"No snapshot found, replaying all events")
            return OrderAggregate.load_from_history(order_id)
    
    def save_account_snapshot(self, account: BankAccountAggregate):
        """Save snapshot untuk BankAccount aggregate"""
        state = {
            "account_id": account.account_id,
            "owner_name": account.owner_name,
            "balance": account.balance,
            "is_active": account.is_active,
            "transaction_count": len(account.transactions)
        }
        
        snapshot_store.save_snapshot(
            aggregate_id=account.account_id,
            state=state,
            version=account.version
        )
        
        print(f"✓ Snapshot saved for {account.account_id} at version {account.version}")


class SnapshotScheduler:
    """
    Background scheduler untuk create snapshots.
    
    Dalam production, ini bisa dijadikan cron job atau background worker.
    """
    
    def __init__(self, snapshot_threshold: int = 100):
        self.manager = SnapshotManager(snapshot_threshold)
    
    def snapshot_all_aggregates(self, aggregate_type: str):
        """
        Snapshot semua aggregates dari type tertentu.
        
        Biasanya dijalankan sebagai background job.
        """
        aggregate_ids = event_store.get_aggregate_ids(aggregate_type)
        
        snapshots_created = 0
        
        for agg_id in aggregate_ids:
            if self.manager.should_snapshot(agg_id):
                if aggregate_type == "Order":
                    order = OrderAggregate.load_from_history(agg_id)
                    if order:
                        self.manager.save_order_snapshot(order)
                        snapshots_created += 1
                
                elif aggregate_type == "BankAccount":
                    account = BankAccountAggregate.load_from_history(agg_id)
                    if account:
                        self.manager.save_account_snapshot(account)
                        snapshots_created += 1
        
        print(f"\n✓ Created {snapshots_created} snapshots for {aggregate_type}")
        return snapshots_created


if __name__ == "__main__":
    print("=== Snapshot Optimization Demo ===\n")
    
    from example_order import OrderItem
    import time
    
    # 1. Create order dengan many events
    print("1. Creating order dengan banyak events...")
    items = [OrderItem("prod_1", "Item1", 1, 100000)]
    order = OrderAggregate.create(
        order_id="order_snapshot_001",
        customer_id="cust_123",
        items=items,
        shipping_address={"city": "Jakarta"}
    )
    
    # Simulate many state changes
    order.process_payment("credit_card", 100000)
    order.ship_order("TRACK-123")
    order.deliver_order()
    
    print(f"   Order version: {order.version}")
    
    # 2. Load tanpa snapshot
    print("\n2. Loading tanpa snapshot...")
    start = time.time()
    loaded_no_snapshot = OrderAggregate.load_from_history("order_snapshot_001")
    time_no_snapshot = time.time() - start
    print(f"   Time: {time_no_snapshot*1000:.2f}ms")
    print(f"   Events replayed: {loaded_no_snapshot.version}")
    
    # 3. Create snapshot
    print("\n3. Creating snapshot...")
    manager = SnapshotManager(snapshot_threshold=2)  # Low threshold for demo
    manager.save_order_snapshot(order)
    
    # 4. Load dengan snapshot
    print("\n4. Loading dengan snapshot optimization...")
    start = time.time()
    loaded_with_snapshot = manager.load_order_with_snapshot("order_snapshot_001")
    time_with_snapshot = time.time() - start
    print(f"   Time: {time_with_snapshot*1000:.2f}ms")
    
    # 5. Compare
    print("\n5. Performance comparison:")
    print(f"   Without snapshot: {time_no_snapshot*1000:.2f}ms")
    print(f"   With snapshot:    {time_with_snapshot*1000:.2f}ms")
    
    if time_with_snapshot < time_no_snapshot:
        speedup = time_no_snapshot / time_with_snapshot
        print(f"   Speedup: {speedup:.2f}x faster! 🚀")
    
    # 6. Verify correctness
    print("\n6. Verifying correctness...")
    assert loaded_no_snapshot.status == loaded_with_snapshot.status
    assert loaded_no_snapshot.total == loaded_with_snapshot.total
    assert loaded_no_snapshot.version == loaded_with_snapshot.version
    print("   ✓ Both methods produce same result")
    
    # 7. Snapshot scheduler demo
    print("\n7. Testing snapshot scheduler...")
    
    # Create more orders
    for i in range(3):
        items = [OrderItem(f"prod_{i}", f"Item{i}", 1, 100000)]
        OrderAggregate.create(
            order_id=f"order_batch_{i}",
            customer_id="cust_123",
            items=items,
            shipping_address={"city": "Jakarta"}
        )
    
    scheduler = SnapshotScheduler(snapshot_threshold=1)
    snapshots_created = scheduler.snapshot_all_aggregates("Order")
    
    # 8. Snapshot retention strategy
    print("\n8. Snapshot retention strategy:")
    print("   - Keep last N snapshots per aggregate")
    print("   - Delete snapshots older than X days")
    print("   - Compress old snapshots")
    print("   - Archive to cold storage")
    
    print("\n✅ Snapshot optimization demo completed!")
    print("\n💡 Best Practices:")
    print("   - Snapshot every 50-100 events")
    print("   - Run snapshot creation in background")
    print("   - Keep multiple snapshots for rollback")
    print("   - Monitor snapshot size and frequency")
