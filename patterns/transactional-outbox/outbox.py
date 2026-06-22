import os
import sqlite3
import time
import uuid
import json
import logging
from typing import Dict, Any, List, Optional
import threading

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("outbox")

class OutboxEvent:
    def __init__(self, aggregate_type: str, aggregate_id: str, event_type: str, payload: dict, id: str = None):
        self.id = id or str(uuid.uuid4())
        self.aggregate_type = aggregate_type
        self.aggregate_id = aggregate_id
        self.event_type = event_type
        self.payload = payload

class OrderService:
    def __init__(self, db_path: str = "app.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            # Create orders table and outbox table atomically (in the same database)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    id TEXT PRIMARY KEY,
                    customer_id TEXT NOT NULL,
                    amount REAL NOT NULL,
                    status TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS outbox_events (
                    id TEXT PRIMARY KEY,
                    aggregate_type TEXT NOT NULL,
                    aggregate_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'PENDING',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    processed_at TIMESTAMP
                )
            """)
            conn.commit()

    def create_order(self, customer_id: str, amount: float) -> str:
        order_id = str(uuid.uuid4())
        
        # We perform order creation and event insert atomically in a database transaction
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("BEGIN TRANSACTION")
            try:
                # 1. State modification (Insert order)
                conn.execute(
                    "INSERT INTO orders (id, customer_id, amount, status) VALUES (?, ?, ?, ?)",
                    (order_id, customer_id, amount, "CREATED")
                )
                
                # 2. Append event to outbox table
                event_id = str(uuid.uuid4())
                payload = json.dumps({
                    "order_id": order_id,
                    "customer_id": customer_id,
                    "amount": amount,
                    "status": "CREATED"
                })
                conn.execute(
                    "INSERT INTO outbox_events (id, aggregate_type, aggregate_id, event_type, payload) VALUES (?, ?, ?, ?, ?)",
                    (event_id, "Order", order_id, "OrderCreated", payload)
                )
                conn.commit()
                logger.info(f"Order {order_id} created successfully and Outbox event written.")
                return order_id
            except Exception as e:
                conn.rollback()
                logger.error(f"Failed to create order: {e}")
                raise e

class EventPublisher:
    """Mock Message Broker Client simulating external message broker (RabbitMQ / Kafka)"""
    def __init__(self, simulate_network_fail: bool = False):
        self.published_events = []
        self.simulate_network_fail = simulate_network_fail

    def publish(self, event_id: str, topic: str, message: dict) -> bool:
        if self.simulate_network_fail:
            # Random simulation or predictable failure
            logger.warning(f"Network Outage! Failed to publish event {event_id} to {topic}.")
            return False
        
        logger.info(f"Published event {event_id} to [{topic}]: {message}")
        self.published_events.append({"event_id": event_id, "topic": topic, "message": message})
        return True

class MessageRelay:
    """Outbox pattern message relay (Transaction Log Miner or Polling Publisher pattern)"""
    def __init__(self, publisher: EventPublisher, db_path: str = "app.db", poll_interval: float = 1.0):
        self.publisher = publisher
        self.db_path = db_path
        self.poll_interval = poll_interval
        self.running = False
        self.thread = None

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        logger.info("Message Relay daemon started.")

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join()
        logger.info("Message Relay daemon stopped.")

    def _run(self):
        while self.running:
            try:
                self.poll_and_publish()
            except Exception as e:
                logger.error(f"Error during message relay polling: {e}")
            time.sleep(self.poll_interval)

    def poll_and_publish(self):
        """Polls pending events, publishes them, and flags them as processed in a loop/transaction"""
        with sqlite3.connect(self.db_path) as conn:
            # 1. Fetch pending events
            # We use SELECT FOR UPDATE style pattern if distributed. Here sqlite is single-threaded connection.
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, aggregate_type, aggregate_id, event_type, payload FROM outbox_events WHERE status = 'PENDING' ORDER BY created_at ASC LIMIT 10"
            )
            rows = cursor.fetchall()
            
            if not rows:
                return

            for row in rows:
                event_id, aggregate_type, aggregate_id, event_type, payload_str = row
                payload = json.loads(payload_str)
                topic = f"{aggregate_type.lower()}-events"
                
                # 2. Attempt publish to broker
                success = self.publisher.publish(
                    event_id=event_id,
                    topic=topic,
                    message={
                        "event_id": event_id,
                        "type": event_type,
                        "aggregate_id": aggregate_id,
                        "data": payload
                    }
                )
                
                if success:
                    # 3. Mark event as processed on success
                    conn.execute(
                        "UPDATE outbox_events SET status = 'PROCESSED', processed_at = CURRENT_TIMESTAMP WHERE id = ?",
                        (event_id,)
                    )
                    conn.commit()
                    logger.info(f"Outbox event {event_id} processed and updated in store.")
                else:
                    logger.warning(f"Retrying event {event_id} in next polling cycle.")
