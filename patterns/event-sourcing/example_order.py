"""
Order Management dengan Event Sourcing

Contoh lengkap implementasi order management system menggunakan Event Sourcing pattern.
Mencakup: Aggregate, Commands, Events, dan Event Handlers.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict
from datetime import datetime
from enum import Enum
from event_store import event_store, Event


class OrderStatus(Enum):
    """Status order dalam lifecycle"""
    PENDING = "pending"
    PAID = "paid"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


@dataclass
class OrderItem:
    """Item dalam order"""
    product_id: str
    product_name: str
    quantity: int
    price: float
    
    def to_dict(self) -> dict:
        return {
            "productId": self.product_id,
            "productName": self.product_name,
            "quantity": self.quantity,
            "price": self.price
        }


class OrderAggregate:
    """
    Order Aggregate - menerima commands dan menghasilkan events.
    
    State dibangun dari events (event sourcing).
    Business logic ada di sini untuk enforce invariants.
    """
    
    def __init__(self, order_id: str):
        self.order_id = order_id
        self.customer_id: Optional[str] = None
        self.items: List[OrderItem] = []
        self.total: float = 0.0
        self.status: OrderStatus = OrderStatus.PENDING
        self.payment_method: Optional[str] = None
        self.shipping_address: Optional[dict] = None
        self.tracking_number: Optional[str] = None
        self.version: int = 0
        
        # Untuk event replay
        self._uncommitted_events: List[Event] = []
    
    @classmethod
    def create(
        cls,
        order_id: str,
        customer_id: str,
        items: List[OrderItem],
        shipping_address: dict
    ) -> 'OrderAggregate':
        """
        Command: Buat order baru
        
        Business rules:
        - Order harus punya minimal 1 item
        - Total harus > 0
        """
        # Validasi
        if not items:
            raise ValueError("Order must have at least one item")
        
        total = sum(item.price * item.quantity for item in items)
        if total <= 0:
            raise ValueError("Order total must be greater than 0")
        
        # Create aggregate
        order = cls(order_id)
        
        # Generate event
        event_data = {
            "orderId": order_id,
            "customerId": customer_id,
            "items": [item.to_dict() for item in items],
            "total": total,
            "shippingAddress": shipping_address
        }
        
        event = event_store.append(
            aggregate_id=order_id,
            aggregate_type="Order",
            event_type="OrderPlaced",
            data=event_data,
            expected_version=0
        )
        
        # Apply event ke state
        order._apply_order_placed(event)
        
        return order
    
    def process_payment(self, payment_method: str, amount: float):
        """
        Command: Proses pembayaran
        
        Business rules:
        - Order harus dalam status PENDING
        - Amount harus sama dengan total order
        """
        if self.status != OrderStatus.PENDING:
            raise ValueError(f"Cannot process payment for order with status {self.status.value}")
        
        if amount != self.total:
            raise ValueError(f"Payment amount {amount} does not match order total {self.total}")
        
        event_data = {
            "orderId": self.order_id,
            "paymentMethod": payment_method,
            "amount": amount
        }
        
        event = event_store.append(
            aggregate_id=self.order_id,
            aggregate_type="Order",
            event_type="PaymentReceived",
            data=event_data,
            expected_version=self.version
        )
        
        self._apply_payment_received(event)
    
    def ship_order(self, tracking_number: str):
        """
        Command: Kirim order
        
        Business rules:
        - Order harus sudah dibayar
        """
        if self.status != OrderStatus.PAID:
            raise ValueError(f"Cannot ship order with status {self.status.value}")
        
        event_data = {
            "orderId": self.order_id,
            "trackingNumber": tracking_number
        }
        
        event = event_store.append(
            aggregate_id=self.order_id,
            aggregate_type="Order",
            event_type="OrderShipped",
            data=event_data,
            expected_version=self.version
        )
        
        self._apply_order_shipped(event)
    
    def deliver_order(self):
        """
        Command: Tandai order sebagai delivered
        
        Business rules:
        - Order harus dalam status SHIPPED
        """
        if self.status != OrderStatus.SHIPPED:
            raise ValueError(f"Cannot deliver order with status {self.status.value}")
        
        event_data = {
            "orderId": self.order_id,
            "deliveredAt": datetime.utcnow().isoformat()
        }
        
        event = event_store.append(
            aggregate_id=self.order_id,
            aggregate_type="Order",
            event_type="OrderDelivered",
            data=event_data,
            expected_version=self.version
        )
        
        self._apply_order_delivered(event)
    
    def cancel_order(self, reason: str):
        """
        Command: Cancel order
        
        Business rules:
        - Order tidak bisa dibatalkan jika sudah shipped
        """
        if self.status in [OrderStatus.SHIPPED, OrderStatus.DELIVERED]:
            raise ValueError(f"Cannot cancel order with status {self.status.value}")
        
        event_data = {
            "orderId": self.order_id,
            "reason": reason,
            "cancelledAt": datetime.utcnow().isoformat()
        }
        
        event = event_store.append(
            aggregate_id=self.order_id,
            aggregate_type="Order",
            event_type="OrderCancelled",
            data=event_data,
            expected_version=self.version
        )
        
        self._apply_order_cancelled(event)
    
    # Event Handlers (Apply events ke state)
    
    def _apply_order_placed(self, event: Event):
        """Apply OrderPlaced event"""
        data = event.data
        self.customer_id = data["customerId"]
        self.items = [
            OrderItem(
                product_id=item["productId"],
                product_name=item["productName"],
                quantity=item["quantity"],
                price=item["price"]
            )
            for item in data["items"]
        ]
        self.total = data["total"]
        self.shipping_address = data["shippingAddress"]
        self.status = OrderStatus.PENDING
        self.version = event.version
    
    def _apply_payment_received(self, event: Event):
        """Apply PaymentReceived event"""
        data = event.data
        self.payment_method = data["paymentMethod"]
        self.status = OrderStatus.PAID
        self.version = event.version
    
    def _apply_order_shipped(self, event: Event):
        """Apply OrderShipped event"""
        data = event.data
        self.tracking_number = data["trackingNumber"]
        self.status = OrderStatus.SHIPPED
        self.version = event.version
    
    def _apply_order_delivered(self, event: Event):
        """Apply OrderDelivered event"""
        self.status = OrderStatus.DELIVERED
        self.version = event.version
    
    def _apply_order_cancelled(self, event: Event):
        """Apply OrderCancelled event"""
        self.status = OrderStatus.CANCELLED
        self.version = event.version
    
    @classmethod
    def load_from_history(cls, order_id: str) -> Optional['OrderAggregate']:
        """
        Load aggregate dari event history (Event Sourcing!)
        
        Ini adalah core dari Event Sourcing: state dibangun dari replay events.
        """
        events = event_store.get_events(order_id)
        
        if not events:
            return None
        
        order = cls(order_id)
        
        for event in events:
            # Dispatch ke event handler yang sesuai
            if event.event_type == "OrderPlaced":
                order._apply_order_placed(event)
            elif event.event_type == "PaymentReceived":
                order._apply_payment_received(event)
            elif event.event_type == "OrderShipped":
                order._apply_order_shipped(event)
            elif event.event_type == "OrderDelivered":
                order._apply_order_delivered(event)
            elif event.event_type == "OrderCancelled":
                order._apply_order_cancelled(event)
        
        return order
    
    def to_dict(self) -> dict:
        """Serialize state untuk debugging/display"""
        return {
            "orderId": self.order_id,
            "customerId": self.customer_id,
            "items": [item.to_dict() for item in self.items],
            "total": self.total,
            "status": self.status.value,
            "paymentMethod": self.payment_method,
            "shippingAddress": self.shipping_address,
            "trackingNumber": self.tracking_number,
            "version": self.version
        }


# Projection: Order List View (untuk display di UI)
class OrderListProjection:
    """
    Read model untuk list view orders.
    
    Projection adalah view yang dibangun dari events.
    Bisa dibuat ulang kapan saja dari event log.
    """
    
    def __init__(self):
        self.orders: Dict[str, dict] = {}
    
    def handle_order_placed(self, event: Event):
        """Handle OrderPlaced event"""
        data = event.data
        self.orders[data["orderId"]] = {
            "orderId": data["orderId"],
            "customerId": data["customerId"],
            "total": data["total"],
            "status": "pending",
            "createdAt": event.timestamp
        }
    
    def handle_payment_received(self, event: Event):
        """Handle PaymentReceived event"""
        order_id = event.data["orderId"]
        if order_id in self.orders:
            self.orders[order_id]["status"] = "paid"
    
    def handle_order_shipped(self, event: Event):
        """Handle OrderShipped event"""
        order_id = event.data["orderId"]
        if order_id in self.orders:
            self.orders[order_id]["status"] = "shipped"
            self.orders[order_id]["trackingNumber"] = event.data["trackingNumber"]
    
    def handle_order_delivered(self, event: Event):
        """Handle OrderDelivered event"""
        order_id = event.data["orderId"]
        if order_id in self.orders:
            self.orders[order_id]["status"] = "delivered"
            self.orders[order_id]["deliveredAt"] = event.data["deliveredAt"]
    
    def handle_order_cancelled(self, event: Event):
        """Handle OrderCancelled event"""
        order_id = event.data["orderId"]
        if order_id in self.orders:
            self.orders[order_id]["status"] = "cancelled"
    
    def rebuild_from_events(self):
        """Rebuild projection dari event store"""
        self.orders.clear()
        
        events = event_store.get_all_events(aggregate_type="Order")
        
        for event in events:
            if event.event_type == "OrderPlaced":
                self.handle_order_placed(event)
            elif event.event_type == "PaymentReceived":
                self.handle_payment_received(event)
            elif event.event_type == "OrderShipped":
                self.handle_order_shipped(event)
            elif event.event_type == "OrderDelivered":
                self.handle_order_delivered(event)
            elif event.event_type == "OrderCancelled":
                self.handle_order_cancelled(event)
    
    def get_all_orders(self) -> List[dict]:
        """Get all orders"""
        return list(self.orders.values())
    
    def get_orders_by_customer(self, customer_id: str) -> List[dict]:
        """Get orders by customer"""
        return [
            order for order in self.orders.values()
            if order["customerId"] == customer_id
        ]
    
    def get_orders_by_status(self, status: str) -> List[dict]:
        """Get orders by status"""
        return [
            order for order in self.orders.values()
            if order["status"] == status
        ]


if __name__ == "__main__":
    print("=== Order Management dengan Event Sourcing ===\n")
    
    # 1. Create new order
    print("1. Membuat order baru...")
    items = [
        OrderItem("prod_1", "Laptop", 1, 15000000),
        OrderItem("prod_2", "Mouse", 2, 250000)
    ]
    
    order = OrderAggregate.create(
        order_id="order_001",
        customer_id="cust_123",
        items=items,
        shipping_address={
            "street": "Jl. Sudirman No. 123",
            "city": "Jakarta",
            "postalCode": "12190"
        }
    )
    
    print(f"   Order created: {order.order_id}")
    print(f"   Status: {order.status.value}")
    print(f"   Total: Rp {order.total:,.0f}")
    
    # 2. Process payment
    print("\n2. Memproses pembayaran...")
    order.process_payment("credit_card", order.total)
    print(f"   Payment received: {order.payment_method}")
    print(f"   Status: {order.status.value}")
    
    # 3. Ship order
    print("\n3. Mengirim order...")
    order.ship_order("TRACK-12345")
    print(f"   Tracking number: {order.tracking_number}")
    print(f"   Status: {order.status.value}")
    
    # 4. Deliver order
    print("\n4. Order delivered...")
    order.deliver_order()
    print(f"   Status: {order.status.value}")
    
    # 5. Load from history (Event Sourcing magic!)
    print("\n5. Loading order dari event history...")
    loaded_order = OrderAggregate.load_from_history("order_001")
    
    if loaded_order:
        print(f"   Order loaded: {loaded_order.order_id}")
        print(f"   Status: {loaded_order.status.value}")
        print(f"   Version: {loaded_order.version}")
        print(f"   Events replayed: {loaded_order.version} events")
    
    # 6. View event history
    print("\n6. Event history untuk order_001:")
    events = event_store.get_events("order_001")
    for event in events:
        print(f"   v{event.version}: {event.event_type} @ {event.timestamp}")
    
    # 7. Projection demo
    print("\n7. Building projection (Order List View)...")
    projection = OrderListProjection()
    projection.rebuild_from_events()
    
    all_orders = projection.get_all_orders()
    print(f"   Total orders in projection: {len(all_orders)}")
    for order_view in all_orders:
        print(f"   - {order_view['orderId']}: {order_view['status']} (Rp {order_view['total']:,.0f})")
    
    # 8. Demo validation rules
    print("\n8. Testing business rules...")
    
    # Create another order
    order2 = OrderAggregate.create(
        order_id="order_002",
        customer_id="cust_456",
        items=[OrderItem("prod_3", "Keyboard", 1, 500000)],
        shipping_address={"street": "Jl. Thamrin", "city": "Jakarta", "postalCode": "10230"}
    )
    
    try:
        # Try to ship unpaid order (should fail)
        order2.ship_order("TRACK-999")
    except ValueError as e:
        print(f"   ✓ Business rule enforced: {e}")
    
    # Pay and ship
    order2.process_payment("bank_transfer", 500000)
    order2.ship_order("TRACK-67890")
    
    try:
        # Try to cancel shipped order (should fail)
        order2.cancel_order("Changed mind")
    except ValueError as e:
        print(f"   ✓ Business rule enforced: {e}")
    
    # 9. Temporal query - state pada titik waktu tertentu
    print("\n9. Temporal query - Order state pada version 2...")
    events_v2 = event_store.get_events("order_001", to_version=1)  # Version 1-2
    
    order_at_v2 = OrderAggregate("order_001")
    for event in events_v2:
        if event.event_type == "OrderPlaced":
            order_at_v2._apply_order_placed(event)
        elif event.event_type == "PaymentReceived":
            order_at_v2._apply_payment_received(event)
    
    print(f"   Status at version 2: {order_at_v2.status.value}")
    print(f"   (Current status: {loaded_order.status.value})")
    
    print("\n✅ Demo completed! Event Sourcing in action.")
