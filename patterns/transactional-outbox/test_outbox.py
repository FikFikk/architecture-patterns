import os
import unittest
import sqlite3
import time
from outbox import OrderService, EventPublisher, MessageRelay

DB_FILE = "test_app.db"

class TestTransactionalOutbox(unittest.TestCase):
    def setUp(self):
        # Ensure a clean database for each test runner
        if os.path.exists(DB_FILE):
            os.remove(DB_FILE)
        self.order_service = OrderService(db_path=DB_FILE)

    def tearDown(self):
        if os.path.exists(DB_FILE):
            os.remove(DB_FILE)

    def test_atomic_order_and_outbox_insertion(self):
        # 1. Place order
        customer_id = "cust-123"
        order_amount = 250.0
        order_id = self.order_service.create_order(customer_id, order_amount)
        
        # 2. Check Order Table
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT customer_id, amount, status FROM orders WHERE id = ?", (order_id,))
            order = cursor.fetchone()
            self.assertIsNotNone(order)
            self.assertEqual(order[0], customer_id)
            self.assertEqual(order[1], order_amount)
            self.assertEqual(order[2], "CREATED")

            # 3. Check Outbox Table
            cursor.execute("SELECT aggregate_id, event_type, status FROM outbox_events WHERE aggregate_id = ?", (order_id,))
            outbox = cursor.fetchone()
            self.assertIsNotNone(outbox)
            self.assertEqual(outbox[0], order_id)
            self.assertEqual(outbox[1], "OrderCreated")
            self.assertEqual(outbox[2], "PENDING")

    def test_message_relay_delivery_success(self):
        # Arrange
        customer_id = "cust-456"
        order_id = self.order_service.create_order(customer_id, 120.0)
        
        publisher = EventPublisher(simulate_network_fail=False)
        relay = MessageRelay(publisher, db_path=DB_FILE)
        
        # Act: Manual single-cycle poll
        relay.poll_and_publish()
        
        # Assert
        self.assertEqual(len(publisher.published_events), 1)
        delivered_event = publisher.published_events[0]
        self.assertEqual(delivered_event["message"]["aggregate_id"], order_id)
        self.assertEqual(delivered_event["topic"], "order-events")
        
        # Outbox event status checking in database
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT status FROM outbox_events WHERE aggregate_id = ?", (order_id,))
            status = cursor.fetchone()[0]
            self.assertEqual(status, "PROCESSED")

    def test_message_relay_network_failure_resilience(self):
        # Arrange
        customer_id = "cust-789"
        order_id = self.order_service.create_order(customer_id, 99.0)
        
        # Simulate fail network publisher
        failed_publisher = EventPublisher(simulate_network_fail=True)
        relay = MessageRelay(failed_publisher, db_path=DB_FILE)
        
        # Act
        relay.poll_and_publish()
        
        # Assert: Event must NOT be published, and state in outbox remains PENDING
        self.assertEqual(len(failed_publisher.published_events), 0)
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT status FROM outbox_events WHERE aggregate_id = ?", (order_id,))
            status = cursor.fetchone()[0]
            self.assertEqual(status, "PENDING")
            
        # Repair network connection
        failed_publisher.simulate_network_fail = False
        
        # Poll again
        relay.poll_and_publish()
        
        # Event should now be successfully published
        self.assertEqual(len(failed_publisher.published_events), 1)
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT status FROM outbox_events WHERE aggregate_id = ?", (order_id,))
            status = cursor.fetchone()[0]
            self.assertEqual(status, "PROCESSED")

if __name__ == "__main__":
    unittest.main()
