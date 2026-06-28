import time

def simulate_ecommerce_saga(should_fail_at: str = None):
    from saga import SagaOrchestrator, SagaStatus

    print(f"\n--- MENJALANKAN SIMULASI SAGA E-COMMERCE (Fail At: {should_fail_at or 'None'}) ---")
    
    # Fake database & services state
    orders_db = {}
    payments_db = {}
    inventory_db = {"laptop": 5}

    # Step 1: Create Order Service
    def create_order(ctx):
        order_id = f"ORD-{int(time.time() * 1000)}"
        orders_db[order_id] = {"item": ctx["item"], "qty": ctx["qty"], "status": "CREATED"}
        print(f"[Order Service] Order {order_id} berhasil dibuat dengan status CREATED.")
        return {"order_id": order_id}

    def cancel_order(ctx):
        order_id = ctx.get("order_id")
        if order_id in orders_db:
            orders_db[order_id]["status"] = "CANCELLED"
            print(f"[Order Service] Kompensasi: Order {order_id} diubah statusnya menjadi CANCELLED.")
        return True

    # Step 2: Payment Service
    def process_payment(ctx):
        if should_fail_at == "payment":
            print("[Payment Service] KESALAHAN: Kartu kredit ditolak / Saldo tidak cukup!")
            raise Exception("Payment failed: Insufficient funds")
        
        payment_id = f"PAY-{int(time.time() * 1000)}"
        payments_db[payment_id] = {"order_id": ctx["order_id"], "amount": ctx["amount"], "status": "CHARGED"}
        print(f"[Payment Service] Pembayaran {payment_id} sebesar Rp{ctx['amount']:,} BERHASIL diproses.")
        return {"payment_id": payment_id}

    def refund_payment(ctx):
        payment_id = ctx.get("payment_id")
        if payment_id in payments_db:
            payments_db[payment_id]["status"] = "REFUNDED"
            print(f"[Payment Service] Kompensasi: Dana untuk Pembayaran {payment_id} BERHASIL di-refund.")
        return True

    # Step 3: Inventory Service
    def reserve_inventory(ctx):
        item = ctx["item"]
        qty = ctx["qty"]
        if should_fail_at == "inventory":
            print(f"[Inventory Service] KESALAHAN: Stok {item} tiba-tiba habis di warehouse!")
            raise Exception("Inventory allocation failed: Out of stock")
        
        inventory_db[item] -= qty
        print(f"[Inventory Service] Stok {item} sebanyak {qty} unit berhasil dialokasikan. Sisa stok: {inventory_db[item]}")
        return {"inventory_reserved": True}

    def release_inventory(ctx):
        item = ctx["item"]
        qty = ctx["qty"]
        inventory_db[item] += qty
        print(f"[Inventory Service] Kompensasi: Stok {item} sebanyak {qty} unit BERHASIL dikembalikan ke warehouse.")
        return True

    orchestrator = SagaOrchestrator()
    orchestrator.add_step("create_order", create_order, cancel_order)
    orchestrator.add_step("process_payment", process_payment, refund_payment)
    orchestrator.add_step("reserve_inventory", reserve_inventory, release_inventory)

    initial_request = {"user_id": "user_123", "item": "laptop", "qty": 1, "amount": 15000000}
    saga_result = orchestrator.execute(initial_request)

    print(f"Hasil Akhir Saga: {saga_result.status.value}")
    print(f"State Database Orders: {orders_db}")
    print(f"State Database Payments: {payments_db}")
    print(f"State Database Inventory: {inventory_db}")

if __name__ == "__main__":
    simulate_ecommerce_saga(should_fail_at=None)
    simulate_ecommerce_saga(should_fail_at="inventory")
