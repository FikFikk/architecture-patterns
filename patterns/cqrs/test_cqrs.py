"""
CQRS Pattern - Test Suite
Tests untuk memastikan command, query, dan event flow berjalan dengan benar
"""

import pytest
from example_simple import (
    CreateOrderCommand,
    UpdateOrderStatusCommand,
    OrderWriteModel,
    OrderReadModel,
    EventBus,
    CreateOrderHandler,
    UpdateOrderStatusHandler,
    OrderQueryHandler,
    OrderReadModelUpdater
)


class TestWriteModel:
    """Test write model operations"""
    
    def test_create_order_success(self):
        """Test create order dengan data valid"""
        write_model = OrderWriteModel()
        
        items = [
            {'product_id': 'P001', 'quantity': 1},
            {'product_id': 'P002', 'quantity': 2}
        ]
        
        order_id = write_model.create_order(
            user_id='USER001',
            items=items,
            address='Jl. Test No. 123'
        )
        
        assert order_id.startswith('ORD')
        assert order_id in write_model.orders
        assert write_model.orders[order_id]['status'] == 'pending'
        assert write_model.orders[order_id]['total'] == 10000000 + (150000 * 2)
    
    def test_create_order_insufficient_stock(self):
        """Test create order dengan stock tidak cukup"""
        write_model = OrderWriteModel()
        
        items = [
            {'product_id': 'P001', 'quantity': 100}  # Stock hanya 10
        ]
        
        with pytest.raises(ValueError, match="Insufficient stock"):
            write_model.create_order(
                user_id='USER001',
                items=items,
                address='Jl. Test No. 123'
            )
    
    def test_create_order_product_not_found(self):
        """Test create order dengan product tidak ada"""
        write_model = OrderWriteModel()
        
        items = [
            {'product_id': 'P999', 'quantity': 1}
        ]
        
        with pytest.raises(ValueError, match="not found"):
            write_model.create_order(
                user_id='USER001',
                items=items,
                address='Jl. Test No. 123'
            )
    
    def test_update_order_status(self):
        """Test update status order"""
        write_model = OrderWriteModel()
        
        # Create order first
        order_id = write_model.create_order(
            user_id='USER001',
            items=[{'product_id': 'P001', 'quantity': 1}],
            address='Jl. Test No. 123'
        )
        
        # Update status
        old_status = write_model.update_order_status(order_id, 'paid')
        
        assert old_status == 'pending'
        assert write_model.orders[order_id]['status'] == 'paid'
    
    def test_update_order_status_not_found(self):
        """Test update status order yang tidak ada"""
        write_model = OrderWriteModel()
        
        with pytest.raises(ValueError, match="not found"):
            write_model.update_order_status('ORD99999', 'paid')


class TestReadModel:
    """Test read model operations"""
    
    def test_get_order_by_id(self):
        """Test get order by ID"""
        read_model = OrderReadModel()
        
        order_data = {
            'order_id': 'ORD00001',
            'user_id': 'USER001',
            'status': 'pending',
            'total': 1000000,
            'item_count': 2,
            'items': []
        }
        
        read_model.update_order(order_data)
        
        result = read_model.get_order_by_id('ORD00001')
        assert result is not None
        assert result['order_id'] == 'ORD00001'
        assert result['user_id'] == 'USER001'
    
    def test_get_orders_by_user(self):
        """Test get orders by user ID"""
        read_model = OrderReadModel()
        
        # Add multiple orders
        for i in range(3):
            read_model.update_order({
                'order_id': f'ORD0000{i+1}',
                'user_id': 'USER001',
                'status': 'pending',
                'total': 1000000,
                'item_count': 1,
                'items': []
            })
        
        # Add order for different user
        read_model.update_order({
            'order_id': 'ORD00004',
            'user_id': 'USER002',
            'status': 'pending',
            'total': 1000000,
            'item_count': 1,
            'items': []
        })
        
        result = read_model.get_orders_by_user('USER001')
        assert len(result) == 3
    
    def test_get_order_summary(self):
        """Test get order summary"""
        read_model = OrderReadModel()
        
        # Add orders with different statuses
        orders = [
            {'order_id': 'ORD00001', 'user_id': 'USER001', 'status': 'pending', 'total': 1000000, 'item_count': 1, 'items': []},
            {'order_id': 'ORD00002', 'user_id': 'USER001', 'status': 'paid', 'total': 2000000, 'item_count': 1, 'items': []},
            {'order_id': 'ORD00003', 'user_id': 'USER001', 'status': 'paid', 'total': 1500000, 'item_count': 1, 'items': []},
        ]
        
        for order in orders:
            read_model.update_order(order)
        
        summary = read_model.get_order_summary('USER001')
        
        assert summary['total_orders'] == 3
        assert summary['total_spent'] == 4500000
        assert summary['orders_by_status']['pending'] == 1
        assert summary['orders_by_status']['paid'] == 2


class TestCommandHandlers:
    """Test command handlers"""
    
    def test_create_order_handler(self):
        """Test CreateOrderHandler"""
        write_model = OrderWriteModel()
        event_bus = EventBus()
        events_received = []
        
        # Subscribe to events
        event_bus.subscribe('OrderCreated', lambda e: events_received.append(e))
        
        handler = CreateOrderHandler(write_model, event_bus)
        
        command = CreateOrderCommand(
            user_id='USER001',
            items=[{'product_id': 'P001', 'quantity': 1}],
            shipping_address='Jl. Test No. 123'
        )
        
        result = handler.handle(command)
        
        assert result['status'] == 'success'
        assert 'order_id' in result
        assert len(events_received) == 1
        assert events_received[0].order_id == result['order_id']
    
    def test_update_order_status_handler(self):
        """Test UpdateOrderStatusHandler"""
        write_model = OrderWriteModel()
        event_bus = EventBus()
        events_received = []
        
        # Create order first
        order_id = write_model.create_order(
            user_id='USER001',
            items=[{'product_id': 'P001', 'quantity': 1}],
            address='Jl. Test No. 123'
        )
        
        # Subscribe to events
        event_bus.subscribe('OrderStatusChanged', lambda e: events_received.append(e))
        
        handler = UpdateOrderStatusHandler(write_model, event_bus)
        
        command = UpdateOrderStatusCommand(
            order_id=order_id,
            status='paid'
        )
        
        result = handler.handle(command)
        
        assert result['status'] == 'success'
        assert len(events_received) == 1
        assert events_received[0].old_status == 'pending'
        assert events_received[0].new_status == 'paid'


class TestEventFlow:
    """Test event flow dari write ke read model"""
    
    def test_end_to_end_order_creation(self):
        """Test flow lengkap: command → event → read model update"""
        # Setup
        write_model = OrderWriteModel()
        read_model = OrderReadModel()
        event_bus = EventBus()
        
        # Setup handlers
        read_model_updater = OrderReadModelUpdater(read_model)
        event_bus.subscribe('OrderCreated', read_model_updater.on_order_created)
        
        create_handler = CreateOrderHandler(write_model, event_bus)
        query_handler = OrderQueryHandler(read_model)
        
        # Execute command
        command = CreateOrderCommand(
            user_id='USER001',
            items=[
                {'product_id': 'P001', 'quantity': 1},
                {'product_id': 'P002', 'quantity': 2}
            ],
            shipping_address='Jl. Test No. 123'
        )
        
        result = create_handler.handle(command)
        order_id = result['order_id']
        
        # Verify write model
        assert order_id in write_model.orders
        assert write_model.orders[order_id]['status'] == 'pending'
        
        # Verify read model (updated via event)
        order_detail = query_handler.get_order_detail(order_id)
        assert order_detail is not None
        assert order_detail['order_id'] == order_id
        assert order_detail['user_id'] == 'USER001'
        assert order_detail['item_count'] == 2
        assert len(order_detail['items']) == 2
    
    def test_end_to_end_status_update(self):
        """Test flow lengkap: update status → event → read model update"""
        # Setup
        write_model = OrderWriteModel()
        read_model = OrderReadModel()
        event_bus = EventBus()
        
        # Setup handlers
        read_model_updater = OrderReadModelUpdater(read_model)
        event_bus.subscribe('OrderCreated', read_model_updater.on_order_created)
        event_bus.subscribe('OrderStatusChanged', read_model_updater.on_order_status_changed)
        
        create_handler = CreateOrderHandler(write_model, event_bus)
        update_handler = UpdateOrderStatusHandler(write_model, event_bus)
        query_handler = OrderQueryHandler(read_model)
        
        # Create order
        command1 = CreateOrderCommand(
            user_id='USER001',
            items=[{'product_id': 'P001', 'quantity': 1}],
            shipping_address='Jl. Test No. 123'
        )
        result = create_handler.handle(command1)
        order_id = result['order_id']
        
        # Update status
        command2 = UpdateOrderStatusCommand(
            order_id=order_id,
            status='paid'
        )
        update_handler.handle(command2)
        
        # Verify read model updated
        order_detail = query_handler.get_order_detail(order_id)
        assert order_detail['status'] == 'paid'
    
    def test_multiple_orders_query(self):
        """Test query multiple orders"""
        # Setup
        write_model = OrderWriteModel()
        read_model = OrderReadModel()
        event_bus = EventBus()
        
        read_model_updater = OrderReadModelUpdater(read_model)
        event_bus.subscribe('OrderCreated', read_model_updater.on_order_created)
        
        create_handler = CreateOrderHandler(write_model, event_bus)
        query_handler = OrderQueryHandler(read_model)
        
        # Create multiple orders
        for i in range(3):
            command = CreateOrderCommand(
                user_id='USER001',
                items=[{'product_id': 'P002', 'quantity': 1}],
                shipping_address=f'Jl. Test No. {i}'
            )
            create_handler.handle(command)
        
        # Query all orders
        orders = query_handler.get_user_orders('USER001')
        assert len(orders) == 3
        
        # Query summary
        summary = query_handler.get_user_summary('USER001')
        assert summary['total_orders'] == 3
        assert summary['orders_by_status']['pending'] == 3


class TestEventualConsistency:
    """Test eventual consistency behavior"""
    
    def test_read_model_catches_up(self):
        """Test bahwa read model eventually consistent dengan write model"""
        write_model = OrderWriteModel()
        read_model = OrderReadModel()
        event_bus = EventBus()
        
        read_model_updater = OrderReadModelUpdater(read_model)
        event_bus.subscribe('OrderCreated', read_model_updater.on_order_created)
        
        create_handler = CreateOrderHandler(write_model, event_bus)
        
        # Create orders
        order_ids = []
        for i in range(5):
            command = CreateOrderCommand(
                user_id='USER001',
                items=[{'product_id': 'P002', 'quantity': 1}],
                shipping_address=f'Jl. Test No. {i}'
            )
            result = create_handler.handle(command)
            order_ids.append(result['order_id'])
        
        # Verify all orders in write model
        assert len(write_model.orders) == 5
        
        # Verify all orders eventually in read model
        assert len(read_model.orders) == 5
        
        # Verify consistency
        for order_id in order_ids:
            write_order = write_model.orders[order_id]
            read_order = read_model.orders[order_id]
            
            assert write_order['user_id'] == read_order['user_id']
            assert write_order['status'] == read_order['status']
            assert write_order['total'] == read_order['total']


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--cov=example_simple', '--cov-report=term-missing'])
