"""
Event Store Implementation

In-memory event store untuk demonstrasi Event Sourcing pattern.
Untuk production, gunakan EventStoreDB, Kafka, atau database yang sesuai.
"""

from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass, field
import json
from uuid import uuid4


@dataclass
class Event:
    """Event domain yang immutable"""
    event_id: str
    event_type: str
    aggregate_id: str
    aggregate_type: str
    data: dict
    metadata: dict
    timestamp: str
    version: int
    
    def to_dict(self) -> dict:
        return {
            "eventId": self.event_id,
            "eventType": self.event_type,
            "aggregateId": self.aggregate_id,
            "aggregateType": self.aggregate_type,
            "data": self.data,
            "metadata": self.metadata,
            "timestamp": self.timestamp,
            "version": self.version
        }


class EventStore:
    """
    Simple in-memory event store.
    
    Features:
    - Append-only writes
    - Get events by aggregate ID
    - Get events from specific version
    - Get all events (for projections)
    """
    
    def __init__(self):
        # {aggregate_id: [Event]}
        self._events: Dict[str, List[Event]] = {}
        # Global event stream untuk subscriptions
        self._global_stream: List[Event] = []
    
    def append(
        self,
        aggregate_id: str,
        aggregate_type: str,
        event_type: str,
        data: dict,
        expected_version: Optional[int] = None,
        metadata: Optional[dict] = None
    ) -> Event:
        """
        Append event ke event store.
        
        Args:
            aggregate_id: ID dari aggregate
            aggregate_type: Tipe aggregate (Order, Account, dll)
            event_type: Tipe event (OrderPlaced, MoneyDeposited, dll)
            data: Event payload
            expected_version: Expected version untuk optimistic concurrency control
            metadata: Additional metadata (user, IP, dll)
        
        Returns:
            Event yang baru disimpan
        
        Raises:
            ConcurrencyError: Jika expected_version tidak match
        """
        if aggregate_id not in self._events:
            self._events[aggregate_id] = []
        
        current_version = len(self._events[aggregate_id])
        
        # Optimistic concurrency control
        if expected_version is not None and expected_version != current_version:
            raise ConcurrencyError(
                f"Expected version {expected_version}, but current version is {current_version}"
            )
        
        event = Event(
            event_id=str(uuid4()),
            event_type=event_type,
            aggregate_id=aggregate_id,
            aggregate_type=aggregate_type,
            data=data,
            metadata=metadata or {},
            timestamp=datetime.utcnow().isoformat(),
            version=current_version + 1
        )
        
        self._events[aggregate_id].append(event)
        self._global_stream.append(event)
        
        return event
    
    def get_events(
        self,
        aggregate_id: str,
        from_version: int = 0,
        to_version: Optional[int] = None
    ) -> List[Event]:
        """
        Ambil events untuk aggregate tertentu.
        
        Args:
            aggregate_id: ID aggregate
            from_version: Mulai dari version (inclusive)
            to_version: Sampai version (inclusive)
        
        Returns:
            List of events
        """
        if aggregate_id not in self._events:
            return []
        
        events = self._events[aggregate_id]
        
        if from_version > 0:
            events = events[from_version:]
        
        if to_version is not None:
            events = events[:to_version + 1]
        
        return events
    
    def get_all_events(
        self,
        aggregate_type: Optional[str] = None,
        from_timestamp: Optional[str] = None
    ) -> List[Event]:
        """
        Ambil semua events (untuk projections dan subscriptions).
        
        Args:
            aggregate_type: Filter by aggregate type
            from_timestamp: Filter events after timestamp
        
        Returns:
            List of all events
        """
        events = self._global_stream
        
        if aggregate_type:
            events = [e for e in events if e.aggregate_type == aggregate_type]
        
        if from_timestamp:
            events = [e for e in events if e.timestamp >= from_timestamp]
        
        return events
    
    def get_aggregate_ids(self, aggregate_type: Optional[str] = None) -> List[str]:
        """Get all aggregate IDs, optionally filtered by type."""
        if aggregate_type:
            return [
                agg_id for agg_id in self._events.keys()
                if self._events[agg_id][0].aggregate_type == aggregate_type
            ]
        return list(self._events.keys())
    
    def get_current_version(self, aggregate_id: str) -> int:
        """Get current version of aggregate."""
        if aggregate_id not in self._events:
            return 0
        return len(self._events[aggregate_id])


class ConcurrencyError(Exception):
    """Raised when optimistic concurrency check fails."""
    pass


class SnapshotStore:
    """
    Simple in-memory snapshot store untuk performance optimization.
    
    Snapshot mengurangi jumlah events yang perlu di-replay untuk load aggregate.
    """
    
    def __init__(self):
        # {aggregate_id: (state, version, timestamp)}
        self._snapshots: Dict[str, tuple] = {}
    
    def save_snapshot(
        self,
        aggregate_id: str,
        state: dict,
        version: int
    ):
        """Save snapshot of aggregate state at specific version."""
        self._snapshots[aggregate_id] = (
            state,
            version,
            datetime.utcnow().isoformat()
        )
    
    def get_snapshot(self, aggregate_id: str) -> Optional[tuple]:
        """
        Get latest snapshot for aggregate.
        
        Returns:
            (state, version) tuple or None if no snapshot exists
        """
        if aggregate_id not in self._snapshots:
            return None
        
        state, version, _ = self._snapshots[aggregate_id]
        return (state, version)
    
    def delete_snapshot(self, aggregate_id: str):
        """Delete snapshot (useful saat rebuild projections)."""
        if aggregate_id in self._snapshots:
            del self._snapshots[aggregate_id]


# Global instances (untuk simplicity, production use dependency injection)
event_store = EventStore()
snapshot_store = SnapshotStore()


if __name__ == "__main__":
    # Demo usage
    print("=== Event Store Demo ===\n")
    
    # Append events
    print("1. Appending events...")
    event_store.append(
        aggregate_id="order_123",
        aggregate_type="Order",
        event_type="OrderPlaced",
        data={"customerId": "cust_456", "items": [{"productId": "prod_1", "quantity": 2}], "total": 100000},
        metadata={"userId": "user_789"}
    )
    
    event_store.append(
        aggregate_id="order_123",
        aggregate_type="Order",
        event_type="PaymentReceived",
        data={"amount": 100000, "method": "credit_card"},
        metadata={"userId": "user_789"}
    )
    
    event_store.append(
        aggregate_id="order_123",
        aggregate_type="Order",
        event_type="OrderShipped",
        data={"trackingNumber": "TRACK123"},
        metadata={"userId": "user_789"}
    )
    
    # Get events
    print("\n2. Retrieving events for order_123...")
    events = event_store.get_events("order_123")
    for event in events:
        print(f"  - {event.event_type} (v{event.version}): {event.data}")
    
    # Get all events
    print("\n3. All events in store:")
    all_events = event_store.get_all_events()
    print(f"  Total events: {len(all_events)}")
    
    # Snapshot demo
    print("\n4. Snapshot demo...")
    snapshot_store.save_snapshot(
        aggregate_id="order_123",
        state={"status": "shipped", "total": 100000},
        version=3
    )
    
    snapshot = snapshot_store.get_snapshot("order_123")
    if snapshot:
        state, version = snapshot
        print(f"  Snapshot at version {version}: {state}")
    
    # Optimistic concurrency
    print("\n5. Optimistic concurrency control...")
    try:
        event_store.append(
            aggregate_id="order_123",
            aggregate_type="Order",
            event_type="OrderCancelled",
            data={"reason": "Customer request"},
            expected_version=2  # Wrong version!
        )
    except ConcurrencyError as e:
        print(f"  ✓ Concurrency error caught: {e}")
    
    print("\n✅ Event Store demo completed!")
