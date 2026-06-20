"""
Unit Tests untuk Event Sourcing Pattern

Test coverage:
- Event Store operations
- Aggregate commands dan business rules
- Event replay
- Projections
- Concurrency control
"""

import pytest
from event_store import EventStore, Event, ConcurrencyError, SnapshotStore
from example_order import OrderAggregate, OrderItem, OrderStatus, OrderListProjection
from example_bank import BankAccountAggregate, AccountStatementProjection


class TestEventStore:
    """Test Event Store functionality"""
    
    def setup_method(self):
        """Setup untuk setiap test"""
        self.event_store = EventStore()
    
    def test_append_event(self):
        """Test append event ke store"""
        event = self.event_store.append(
            aggregate_id="test_001",
            aggregate_type="TestAggregate",
            event_type="TestEvent",
            data={"value": 123}
        )
        
        assert event.event_id is not None
        assert event.event_type == "TestEvent"
        assert event.aggregate_id == "test_001"
        assert event.data["value"] == 123
        assert event.version == 1
    
    def test_get_events(self):
        """Test retrieve events dari store"""
        # Append multiple events
        for i in range(3):
            self.event_store.append(
                aggregate_id="test_002",
                aggregate_type="TestAggregate",
                event_type=f"Event{i}",
                data={"index": i}
            )
        
        events = self.event_store.get_events("test_002")
        assert len(events) == 3
        assert events[0].version == 1
        assert events[2].version == 3
    
    def test_get_events_from_version(self):
        """Test get events dari version tertentu"""
        for i in range(5):
            self.event_store.append(
                aggregate_id="test_003",
                aggregate_type="TestAggregate",
                event_type=f"Event{i}",
                data={"index": i}
            )
        
        # Get events from version 2
        events = self.event_store.get_events("test_003", from_version=2)
        assert len(events) == 3  # v3, v4, v5
        assert events[0].version == 3
    
    def test_optimistic_concurrency(self):
        """Test optimistic concurrency control"""
        self.event_store.append(
            aggregate_id="test_004",
            aggregate_type="TestAggregate",
            event_type="Event1",
            data={}
        )
        
        # Correct version should succeed
        self.event_store.append(
            aggregate_id="test_004",
            aggregate_type="TestAggregate",
            event_type="Event2",
            data={},
            expected_version=1
        )
        
        # Wrong version should fail
        with pytest.raises(ConcurrencyError):
            self.event_store.append(
                aggregate_id="test_004",
                aggregate_type="TestAggregate",
                event_type="Event3",
                data={},
                expected_version=1  # Wrong! Current is 2
            )


class TestOrderAggregate:
    """Test Order Aggregate dengan Event Sourcing"""
    
    def setup_method(self):
        """Setup untuk setiap test"""
        from event_store import event_store as global_store
        global_store._events.clear()
        global_store._global_stream.clear()
    
    def test_create_order(self):
        """Test create order command"""
        items = [OrderItem("prod_1", "Laptop", 1, 10000000)]
        
        order = OrderAggregate.create(
            order_id="order_test_001",
            customer_id="cust_123",
            items=items,
            shipping_address={"city": "Jakarta"}
        )
        
        assert order.order_id == "order_test_001"
        assert order.customer_id == "cust_123"
        assert order.status == OrderStatus.PENDING
        assert order.total == 10000000
        assert order.version == 1
    
    def test_order_cannot_be_empty(self):
        """Test business rule: order harus punya items"""
        with pytest.raises(ValueError, match="at least one item"):
            OrderAggregate.create(
                order_id="order_test_002",
                customer_id="cust_123",
                items=[],  # Empty!
                shipping_address={"city": "Jakarta"}
            )
    
    def test_process_payment(self):
        """Test payment processing"""
        items = [OrderItem("prod_1", "Mouse", 1, 250000)]
        order = OrderAggregate.create(
            order_id="order_test_003",
            customer_id="cust_123",
            items=items,
            shipping_address={"city": "Jakarta"}
        )
        
        order.process_payment("credit_card", 250000)
        
        assert order.status == OrderStatus.PAID
        assert order.payment_method == "credit_card"
        assert order.version == 2
    
    def test_payment_amount_must_match(self):
        """Test business rule: payment amount harus sesuai total"""
        items = [OrderItem("prod_1", "Mouse", 1, 250000)]
        order = OrderAggregate.create(
            order_id="order_test_004",
            customer_id="cust_123",
            items=items,
            shipping_address={"city": "Jakarta"}
        )
        
        with pytest.raises(ValueError, match="does not match"):
            order.process_payment("credit_card", 100000)  # Wrong amount!
    
    def test_ship_order(self):
        """Test shipping order"""
        items = [OrderItem("prod_1", "Keyboard", 1, 500000)]
        order = OrderAggregate.create(
            order_id="order_test_005",
            customer_id="cust_123",
            items=items,
            shipping_address={"city": "Jakarta"}
        )
        
        order.process_payment("bank_transfer", 500000)
        order.ship_order("TRACK-123")
        
        assert order.status == OrderStatus.SHIPPED
        assert order.tracking_number == "TRACK-123"
        assert order.version == 3
    
    def test_cannot_ship_unpaid_order(self):
        """Test business rule: tidak bisa ship order yang belum dibayar"""
        items = [OrderItem("prod_1", "Keyboard", 1, 500000)]
        order = OrderAggregate.create(
            order_id="order_test_006",
            customer_id="cust_123",
            items=items,
            shipping_address={"city": "Jakarta"}
        )
        
        with pytest.raises(ValueError, match="Cannot ship"):
            order.ship_order("TRACK-999")
    
    def test_load_from_history(self):
        """Test event replay (core dari Event Sourcing!)"""
        # Create dan modify order
        items = [OrderItem("prod_1", "Monitor", 1, 3000000)]
        order = OrderAggregate.create(
            order_id="order_test_007",
            customer_id="cust_123",
            items=items,
            shipping_address={"city": "Jakarta"}
        )
        order.process_payment("credit_card", 3000000)
        order.ship_order("TRACK-456")
        order.deliver_order()
        
        # Load dari event history
        loaded = OrderAggregate.load_from_history("order_test_007")
        
        assert loaded is not None
        assert loaded.order_id == "order_test_007"
        assert loaded.status == OrderStatus.DELIVERED
        assert loaded.total == 3000000
        assert loaded.tracking_number == "TRACK-456"
        assert loaded.version == 4


class TestBankAccount:
    """Test Bank Account dengan Event Sourcing"""
    
    def setup_method(self):
        """Setup untuk setiap test"""
        from event_store import event_store as global_store
        global_store._events.clear()
        global_store._global_stream.clear()
    
    def test_open_account(self):
        """Test open account"""
        account = BankAccountAggregate.open_account(
            account_id="ACC-TEST-001",
            owner_name="Test User",
            initial_deposit=1000000
        )
        
        assert account.account_id == "ACC-TEST-001"
        assert account.owner_name == "Test User"
        assert account.balance == 1000000
        assert account.is_active is True
    
    def test_deposit(self):
        """Test deposit money"""
        account = BankAccountAggregate.open_account(
            account_id="ACC-TEST-002",
            owner_name="Test User",
            initial_deposit=500000
        )
        
        account.deposit(200000, "Salary")
        
        assert account.balance == 700000
        assert len(account.transactions) == 2
    
    def test_withdraw(self):
        """Test withdraw money"""
        account = BankAccountAggregate.open_account(
            account_id="ACC-TEST-003",
            owner_name="Test User",
            initial_deposit=1000000
        )
        
        account.withdraw(300000, "ATM")
        
        assert account.balance == 700000
    
    def test_insufficient_balance(self):
        """Test business rule: tidak bisa withdraw lebih dari balance"""
        account = BankAccountAggregate.open_account(
            account_id="ACC-TEST-004",
            owner_name="Test User",
            initial_deposit=100000
        )
        
        with pytest.raises(ValueError, match="Insufficient balance"):
            account.withdraw(200000, "Invalid withdrawal")
    
    def test_close_account(self):
        """Test close account"""
        account = BankAccountAggregate.open_account(
            account_id="ACC-TEST-005",
            owner_name="Test User",
            initial_deposit=100000
        )
        
        # Withdraw all
        account.withdraw(100000, "Withdraw all")
        
        # Close
        account.close_account("Migration")
        
        assert account.is_active is False
    
    def test_cannot_close_with_balance(self):
        """Test business rule: tidak bisa close account dengan balance > 0"""
        account = BankAccountAggregate.open_account(
            account_id="ACC-TEST-006",
            owner_name="Test User",
            initial_deposit=100000
        )
        
        with pytest.raises(ValueError, match="non-zero balance"):
            account.close_account()
    
    def test_temporal_query(self):
        """Test temporal query - balance pada tanggal tertentu"""
        account = BankAccountAggregate.open_account(
            account_id="ACC-TEST-007",
            owner_name="Test User",
            initial_deposit=1000000
        )
        
        account.deposit(500000, "Deposit 1")
        account.withdraw(200000, "Withdrawal 1")
        
        # Current balance
        assert account.balance == 1300000
        
        # Balance at specific version (simulate date)
        from event_store import event_store as global_store
        events = global_store.get_events("ACC-TEST-007", to_version=1)
        
        temp_account = BankAccountAggregate("ACC-TEST-007")
        for event in events:
            if event.event_type == "AccountOpened":
                temp_account._apply_account_opened(event)
        
        assert temp_account.balance == 1000000  # Initial only


class TestProjections:
    """Test Projections (Read Models)"""
    
    def setup_method(self):
        """Setup untuk setiap test"""
        from event_store import event_store as global_store
        global_store._events.clear()
        global_store._global_stream.clear()
    
    def test_order_list_projection(self):
        """Test order list projection"""
        # Create orders
        items1 = [OrderItem("prod_1", "Item1", 1, 100000)]
        OrderAggregate.create("order_p1", "cust_1", items1, {"city": "Jakarta"})
        
        items2 = [OrderItem("prod_2", "Item2", 1, 200000)]
        OrderAggregate.create("order_p2", "cust_2", items2, {"city": "Bandung"})
        
        # Build projection
        projection = OrderListProjection()
        projection.rebuild_from_events()
        
        orders = projection.get_all_orders()
        assert len(orders) == 2
        
        # Test filtering
        cust1_orders = projection.get_orders_by_customer("cust_1")
        assert len(cust1_orders) == 1
        assert cust1_orders[0]["orderId"] == "order_p1"
    
    def test_account_statement_projection(self):
        """Test account statement projection"""
        # Create and use account
        account = BankAccountAggregate.open_account(
            account_id="ACC-PROJ-001",
            owner_name="Test User",
            initial_deposit=1000000
        )
        account.deposit(500000, "Deposit")
        account.withdraw(200000, "Withdrawal")
        
        # Build projection
        projection = AccountStatementProjection()
        projection.rebuild_from_events()
        
        statement = projection.get_statement("ACC-PROJ-001")
        assert len(statement) == 3  # Initial + deposit + withdrawal
        
        # Check balance progression
        assert statement[0]["balance"] == 1000000
        assert statement[1]["balance"] == 1500000
        assert statement[2]["balance"] == 1300000


class TestSnapshots:
    """Test Snapshot functionality"""
    
    def test_save_and_load_snapshot(self):
        """Test snapshot save and load"""
        snapshot_store = SnapshotStore()
        
        state = {"balance": 5000000, "status": "active"}
        snapshot_store.save_snapshot("agg_001", state, version=100)
        
        loaded = snapshot_store.get_snapshot("agg_001")
        assert loaded is not None
        
        loaded_state, loaded_version = loaded
        assert loaded_state["balance"] == 5000000
        assert loaded_version == 100
    
    def test_snapshot_optimization(self):
        """Test snapshot mengurangi jumlah events yang perlu di-replay"""
        from event_store import event_store as global_store, snapshot_store
        
        # Create account with many transactions
        account = BankAccountAggregate.open_account(
            account_id="ACC-SNAP-001",
            owner_name="Test User",
            initial_deposit=1000000
        )
        
        # Many deposits
        for i in range(50):
            account.deposit(10000, f"Deposit {i}")
        
        # Save snapshot at version 25
        snapshot_state = {
            "balance": account.balance,
            "owner_name": account.owner_name,
            "is_active": account.is_active
        }
        snapshot_store.save_snapshot("ACC-SNAP-001", snapshot_state, version=25)
        
        # Load with snapshot (should only replay events after v25)
        snapshot = snapshot_store.get_snapshot("ACC-SNAP-001")
        assert snapshot is not None
        
        state, version = snapshot
        events_after_snapshot = global_store.get_events("ACC-SNAP-001", from_version=version)
        
        # Should have fewer events to replay
        assert len(events_after_snapshot) < 51


if __name__ == "__main__":
    # Run tests dengan pytest
    pytest.main([__file__, "-v", "--tb=short"])
