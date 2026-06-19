"""
CQRS Pattern - Simple Implementation Example
Contoh sederhana untuk memahami konsep dasar CQRS
"""

from dataclasses import dataclass
from datetime import datetime
from typing import List, Dict, Optional
import json


# ============================================================================
# DOMAIN MODELS
# ============================================================================

@dataclass
class Product:
    """Product entity di write model"""
    id: str
    name: str
    price: float
    stock: int


# ============================================================================
# COMMANDS (Write Side)
# ============================================================================

@dataclass
class CreateOrderCommand:
    """Command untuk membuat order baru"""
    user_id: str
    items: List[Dict]  # [{'product_id': str, 'quantity': int}]
    shipping_address: str


@dataclass
class UpdateOrderStatusCommand:
    """Command untuk update status order"""
    order_id: str
    status: str  # pending, paid, shipped, delivered


# ============================================================================
# EVENTS
# ============================================================================

@dataclass
class OrderCreatedEvent:
    """Event yang di-emit setelah order dibuat"""
    order_id: str
    user_id: str
    items: List[Dict]
    total: float
    timestamp: datetime


@dataclass
class OrderStatusChangedEvent:
    """Event yang di-emit setelah status order berubah"""
    order_id: str
    old_status: str
    new_status: str
    timestamp: datetime


# ============================================================================
# EVENT BUS (Simple In-Memory Implementation)
# ============================================================================

class EventBus:
    """Simple event bus untuk demo purposes"""
    
    def __init__(self):
        self.handlers: Dict[str, List] = {}
    
    def subscribe(self, event_type: str, handler):
        """Subscribe handler ke event type tertentu"""
        if event_type not in self.handlers:
            self.handlers[event_type] = []
        self.handlers[event_type].append(handler)
    
    def publish(self, event_type: str, event):
        """Publish event ke semua subscribers"""
        print(f"📢 Publishing event: {event_type}")
        if event_type in self.handlers:
            for handler in self.handlers[event_type]:
                handler(event)


# ============================================================================
# WRITE SIDE - Command Handlers
# ============================================================================

class OrderWriteModel:
    """Write model - normalized data structure"""
    
    def __init__(self):
        # Simulasi database dengan dict
        self.orders: Dict[str, Dict] = {}
        self.order_items: Dict[str, List[Dict]] = {}
        self.products: Dict[str, Product] = self._init_products()
        self._order_counter = 1
    
    def _init_products(self) -> Dict[str, Product]:
        """Initialize sample products"""
        return {
            'P001': Product('P001', 'Laptop', 10000000, 10),
            'P002': Product('P002', 'Mouse', 150000, 50),
            'P003': Product('P003', 'Keyboard', 500000, 30),
        }
    
    def create_order(self, user_id: str, items: List[Dict], address: str) -> str:
        """Create order di write database"""
        order_id = f"ORD{self._order_counter:05d}"
        self._order_counter += 1
        
        # Validate stock
        for item in items:
            product = self.products.get(item['product_id'])
            if not product:
                raise ValueError(f"Product {item['product_id']} not found")
            if product.stock < item['quantity']:
                raise ValueError(f"Insufficient stock for {product.name}")
        
        # Calculate total
        total = sum(
            self.products[item['product_id']].price * item['quantity']
            for item in items
        )
        
        # Save order (normalized)
        self.orders[order_id] = {
            'order_id': order_id,
            'user_id': user_id,
            'status': 'pending',
            'total': total,
            'shipping_address': address,
            'created_at': datetime.now()
        }
        
        # Save order items (separate table)
        self.order_items[order_id] = items
        
        # Update stock
        for item in items:
            self.products[item['product_id']].stock -= item['quantity']
        
        return order_id
    
    def update_order_status(self, order_id: str, new_status: str) -> str:
        """Update order status"""
        if order_id not in self.orders:
            raise ValueError(f"Order {order_id} not found")
        
        old_status = self.orders[order_id]['status']
        self.orders[order_id]['status'] = new_status
        self.orders[order_id]['updated_at'] = datetime.now()
        
        return old_status


class CreateOrderHandler:
    """Handler untuk CreateOrderCommand"""
    
    def __init__(self, write_model: OrderWriteModel, event_bus: EventBus):
        self.write_model = write_model
        self.event_bus = event_bus
    
    def handle(self, command: CreateOrderCommand) -> Dict:
        """Process create order command"""
        print(f"\n🔨 Processing command: CreateOrder")
        print(f"   User: {command.user_id}")
        print(f"   Items: {len(command.items)}")
        
        # Validate
        if not command.items:
            raise ValueError("Order must have at least one item")
        
        # Execute business logic
        order_id = self.write_model.create_order(
            command.user_id,
            command.items,
            command.shipping_address
        )
        
        # Get order details for event
        order = self.write_model.orders[order_id]
        items_with_details = []
        for item in command.items:
            product = self.write_model.products[item['product_id']]
            items_with_details.append({
                'product_id': item['product_id'],
                'product_name': product.name,
                'quantity': item['quantity'],
                'price': product.price
            })
        
        # Publish event
        event = OrderCreatedEvent(
            order_id=order_id,
            user_id=command.user_id,
            items=items_with_details,
            total=order['total'],
            timestamp=datetime.now()
        )
        self.event_bus.publish('OrderCreated', event)
        
        print(f"✅ Order created: {order_id}")
        return {'order_id': order_id, 'status': 'success'}


class UpdateOrderStatusHandler:
    """Handler untuk UpdateOrderStatusCommand"""
    
    def __init__(self, write_model: OrderWriteModel, event_bus: EventBus):
        self.write_model = write_model
        self.event_bus = event_bus
    
    def handle(self, command: UpdateOrderStatusCommand) -> Dict:
        """Process update order status command"""
        print(f"\n🔨 Processing command: UpdateOrderStatus")
        print(f"   Order: {command.order_id}")
        print(f"   New Status: {command.status}")
        
        old_status = self.write_model.update_order_status(
            command.order_id,
            command.status
        )
        
        # Publish event
        event = OrderStatusChangedEvent(
            order_id=command.order_id,
            old_status=old_status,
            new_status=command.status,
            timestamp=datetime.now()
        )
        self.event_bus.publish('OrderStatusChanged', event)
        
        print(f"✅ Status updated: {old_status} → {command.status}")
        return {'status': 'success'}


# ============================================================================
# READ SIDE - Query Models
# ============================================================================

class OrderReadModel:
    """Read model - denormalized data structure untuk performa"""
    
    def __init__(self):
        # Denormalized: semua data dalam satu struktur
        self.orders: Dict[str, Dict] = {}
    
    def update_order(self, order_data: Dict):
        """Update read model dengan data denormalized"""
        self.orders[order_data['order_id']] = order_data
    
    def get_order_by_id(self, order_id: str) -> Optional[Dict]:
        """Get order detail - single query, no joins"""
        return self.orders.get(order_id)
    
    def get_orders_by_user(self, user_id: str) -> List[Dict]:
        """Get all orders for a user - already denormalized"""
        return [
            order for order in self.orders.values()
            if order['user_id'] == user_id
        ]
    
    def get_order_summary(self, user_id: str) -> Dict:
        """Get order summary - pre-computed data"""
        user_orders = self.get_orders_by_user(user_id)
        return {
            'total_orders': len(user_orders),
            'total_spent': sum(order['total'] for order in user_orders),
            'orders_by_status': {
                'pending': len([o for o in user_orders if o['status'] == 'pending']),
                'paid': len([o for o in user_orders if o['status'] == 'paid']),
                'shipped': len([o for o in user_orders if o['status'] == 'shipped']),
                'delivered': len([o for o in user_orders if o['status'] == 'delivered']),
            }
        }


# ============================================================================
# EVENT HANDLERS - Sinkronisasi Write → Read
# ============================================================================

class OrderReadModelUpdater:
    """Event handler yang update read model saat ada perubahan"""
    
    def __init__(self, read_model: OrderReadModel):
        self.read_model = read_model
    
    def on_order_created(self, event: OrderCreatedEvent):
        """Handle OrderCreatedEvent"""
        print(f"📝 Updating read model: OrderCreated")
        
        # Denormalize data untuk read model
        order_data = {
            'order_id': event.order_id,
            'user_id': event.user_id,
            'status': 'pending',
            'total': event.total,
            'item_count': len(event.items),
            'items': event.items,  # Sudah include nama produk
            'created_at': event.timestamp.isoformat(),
            'updated_at': event.timestamp.isoformat()
        }
        
        self.read_model.update_order(order_data)
        print(f"✅ Read model updated")
    
    def on_order_status_changed(self, event: OrderStatusChangedEvent):
        """Handle OrderStatusChangedEvent"""
        print(f"📝 Updating read model: OrderStatusChanged")
        
        order = self.read_model.get_order_by_id(event.order_id)
        if order:
            order['status'] = event.new_status
            order['updated_at'] = event.timestamp.isoformat()
            self.read_model.update_order(order)
            print(f"✅ Read model updated")


# ============================================================================
# QUERY HANDLERS
# ============================================================================

class OrderQueryHandler:
    """Handler untuk queries"""
    
    def __init__(self, read_model: OrderReadModel):
        self.read_model = read_model
    
    def get_order_detail(self, order_id: str) -> Optional[Dict]:
        """Query untuk mendapatkan detail order"""
        print(f"\n🔍 Query: GetOrderDetail({order_id})")
        result = self.read_model.get_order_by_id(order_id)
        if result:
            print(f"✅ Found order: {result['order_id']}")
        else:
            print(f"❌ Order not found")
        return result
    
    def get_user_orders(self, user_id: str) -> List[Dict]:
        """Query untuk mendapatkan semua order user"""
        print(f"\n🔍 Query: GetUserOrders({user_id})")
        result = self.read_model.get_orders_by_user(user_id)
        print(f"✅ Found {len(result)} orders")
        return result
    
    def get_user_summary(self, user_id: str) -> Dict:
        """Query untuk mendapatkan summary user"""
        print(f"\n🔍 Query: GetUserSummary({user_id})")
        result = self.read_model.get_order_summary(user_id)
        print(f"✅ Summary generated")
        return result


# ============================================================================
# DEMO APPLICATION
# ============================================================================

def print_separator():
    print("\n" + "=" * 70 + "\n")


def demo():
    """Demo aplikasi CQRS"""
    
    print("🚀 CQRS Pattern Demo - Simple E-commerce Order System")
    print_separator()
    
    # Initialize components
    event_bus = EventBus()
    write_model = OrderWriteModel()
    read_model = OrderReadModel()
    
    # Setup event handlers
    read_model_updater = OrderReadModelUpdater(read_model)
    event_bus.subscribe('OrderCreated', read_model_updater.on_order_created)
    event_bus.subscribe('OrderStatusChanged', read_model_updater.on_order_status_changed)
    
    # Setup command handlers
    create_order_handler = CreateOrderHandler(write_model, event_bus)
    update_status_handler = UpdateOrderStatusHandler(write_model, event_bus)
    
    # Setup query handler
    query_handler = OrderQueryHandler(read_model)
    
    print("✅ System initialized")
    print_separator()
    
    # Scenario 1: User membuat order
    print("📦 SCENARIO 1: Create Order")
    print_separator()
    
    command1 = CreateOrderCommand(
        user_id='USER001',
        items=[
            {'product_id': 'P001', 'quantity': 1},
            {'product_id': 'P002', 'quantity': 2},
        ],
        shipping_address='Jl. Sudirman No. 123, Jakarta'
    )
    result1 = create_order_handler.handle(command1)
    order_id_1 = result1['order_id']
    
    print_separator()
    
    # Query order yang baru dibuat
    print("📋 Query order yang baru dibuat:")
    order_detail = query_handler.get_order_detail(order_id_1)
    print(json.dumps(order_detail, indent=2, default=str))
    
    print_separator()
    
    # Scenario 2: User membuat order lagi
    print("📦 SCENARIO 2: Create Another Order")
    print_separator()
    
    command2 = CreateOrderCommand(
        user_id='USER001',
        items=[
            {'product_id': 'P003', 'quantity': 1},
        ],
        shipping_address='Jl. Sudirman No. 123, Jakarta'
    )
    result2 = create_order_handler.handle(command2)
    order_id_2 = result2['order_id']
    
    print_separator()
    
    # Scenario 3: Update status order
    print("🔄 SCENARIO 3: Update Order Status")
    print_separator()
    
    command3 = UpdateOrderStatusCommand(
        order_id=order_id_1,
        status='paid'
    )
    update_status_handler.handle(command3)
    
    command4 = UpdateOrderStatusCommand(
        order_id=order_id_1,
        status='shipped'
    )
    update_status_handler.handle(command4)
    
    print_separator()
    
    # Scenario 4: Query user orders
    print("📊 SCENARIO 4: Query User Orders")
    print_separator()
    
    user_orders = query_handler.get_user_orders('USER001')
    print(f"\nUser Orders (Total: {len(user_orders)}):")
    for order in user_orders:
        print(f"  - {order['order_id']}: {order['status']} | Rp {order['total']:,.0f} | {order['item_count']} items")
    
    print_separator()
    
    # Scenario 5: Query user summary
    print("📈 SCENARIO 5: Query User Summary")
    print_separator()
    
    summary = query_handler.get_user_summary('USER001')
    print("\nUser Summary:")
    print(json.dumps(summary, indent=2))
    
    print_separator()
    
    # Show write vs read model difference
    print("🔍 COMPARISON: Write Model vs Read Model")
    print_separator()
    
    print("Write Model (Normalized):")
    print("  Orders table:")
    for order_id, order in write_model.orders.items():
        print(f"    {order_id}: status={order['status']}, total={order['total']}")
    print("\n  Order Items table (separate):")
    for order_id, items in write_model.order_items.items():
        print(f"    {order_id}: {len(items)} items")
    
    print("\nRead Model (Denormalized):")
    print("  All data in one structure:")
    for order_id, order in read_model.orders.items():
        print(f"    {order_id}: status={order['status']}, items={order['item_count']}, total={order['total']}")
        print(f"      Items embedded: {[item['product_name'] for item in order['items']]}")
    
    print_separator()
    
    print("✅ Demo completed!")
    print("\n💡 Key Takeaways:")
    print("  1. Commands mengubah state melalui write model")
    print("  2. Events di-emit setelah perubahan berhasil")
    print("  3. Read model di-update via event handlers")
    print("  4. Queries hanya akses read model (denormalized)")
    print("  5. Write dan read model bisa dioptimasi independen")


if __name__ == '__main__':
    demo()
