import pytest
from saga import SagaOrchestrator, SagaStatus, StepStatus

def test_saga_successful_execution():
    def order_action(ctx):
        return {"order_id": "ORD-123", "order_created": True}

    def order_compensate(ctx):
        return True

    def payment_action(ctx):
        return {"payment_id": "PAY-999", "payment_processed": True}

    def payment_compensate(ctx):
        return True

    def inventory_action(ctx):
        return {"inventory_reserved": True}

    def inventory_compensate(ctx):
        return True

    orchestrator = SagaOrchestrator()
    orchestrator.add_step("create_order", order_action, order_compensate)
    orchestrator.add_step("process_payment", payment_action, payment_compensate)
    orchestrator.add_step("reserve_inventory", inventory_action, inventory_compensate)

    saga = orchestrator.execute({"user_id": "user-1", "amount": 150.0})

    assert saga.status == SagaStatus.SUCCESSFUL
    assert saga.context["order_id"] == "ORD-123"
    assert saga.context["payment_id"] == "PAY-999"
    assert saga.step_statuses["create_order"] == StepStatus.SUCCESS
    assert saga.step_statuses["process_payment"] == StepStatus.SUCCESS
    assert saga.step_statuses["reserve_inventory"] == StepStatus.SUCCESS

def test_saga_rollback_on_failure():
    compensated_steps = []

    def order_action(ctx):
        return {"order_id": "ORD-123"}

    def order_compensate(ctx):
        compensated_steps.append("create_order")
        return True

    def payment_action(ctx):
        return {"payment_id": "PAY-999"}

    def payment_compensate(ctx):
        compensated_steps.append("process_payment")
        return True

    def inventory_action(ctx):
        raise ValueError("Out of stock!")

    def inventory_compensate(ctx):
        compensated_steps.append("reserve_inventory")
        return True

    orchestrator = SagaOrchestrator()
    orchestrator.add_step("create_order", order_action, order_compensate)
    orchestrator.add_step("process_payment", payment_action, payment_compensate)
    orchestrator.add_step("reserve_inventory", inventory_action, inventory_compensate)

    saga = orchestrator.execute({"user_id": "user-1", "item": "laptop"})

    assert saga.status == SagaStatus.COMPENSATED
    assert saga.step_statuses["reserve_inventory"] == StepStatus.FAILED
    assert saga.step_statuses["process_payment"] == StepStatus.COMPENSATED
    assert saga.step_statuses["create_order"] == StepStatus.COMPENSATED
    assert compensated_steps == ["process_payment", "create_order"]

def test_saga_compensation_failure():
    def order_action(ctx):
        return {"order_id": "ORD-123"}

    def order_compensate(ctx):
        return True

    def payment_action(ctx):
        return {"payment_id": "PAY-999"}

    def payment_compensate(ctx):
        raise RuntimeError("Payment gateway network error during refund")

    def inventory_action(ctx):
        raise Exception("Failure in inventory execution")

    def inventory_compensate(ctx):
        return True

    orchestrator = SagaOrchestrator()
    orchestrator.add_step("create_order", order_action, order_compensate)
    orchestrator.add_step("process_payment", payment_action, payment_compensate)
    orchestrator.add_step("reserve_inventory", inventory_action, inventory_compensate)

    saga = orchestrator.execute({"user_id": "user-1"})

    assert saga.status == SagaStatus.FAILED
    assert saga.step_statuses["process_payment"] == StepStatus.COMPENSATION_FAILED
    assert saga.step_statuses["create_order"] == StepStatus.COMPENSATED
