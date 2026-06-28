import time
import threading
import uuid
import json
from enum import Enum
from typing import Dict, Any, List, Optional, Callable

class CompensatingStatus(Enum):
    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"

class StepStatus(Enum):
    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    COMPENSATED = "COMPENSATED"
    COMPENSATION_FAILED = "COMPENSATION_FAILED"

class SagaStatus(Enum):
    PENDING = "PENDING"
    SUCCESSFUL = "SUCCESSFUL"
    FAILED = "FAILED"
    COMPENSATING = "COMPENSATING"
    COMPENSATED = "COMPENSATED"

class SagaStep:
    def __init__(
        self,
        name: str,
        action: Callable[[Dict[str, Any]], Dict[str, Any]],
        compensation: Callable[[Dict[str, Any]], bool]
    ):
        self.name = name
        self.action = action
        self.compensation = compensation

class SagaInstance:
    def __init__(self, saga_id: str, steps: List[SagaStep]):
        self.saga_id = saga_id
        self.steps = steps
        self.status = SagaStatus.PENDING
        self.current_step_index = 0
        self.context: Dict[str, Any] = {}
        self.step_results: Dict[str, Any] = {}
        self.step_statuses: Dict[str, StepStatus] = {step.name: StepStatus.PENDING for step in steps}
        self.lock = threading.Lock()

    def to_dict(self) -> Dict[str, Any]:
        with self.lock:
            return {
                "saga_id": self.saga_id,
                "status": self.status.value,
                "current_step_index": self.current_step_index,
                "context": self.context,
                "step_statuses": {k: v.value for k, v in self.step_statuses.items()}
            }

class SagaOrchestrator:
    def __init__(self):
        self.steps: List[SagaStep] = []

    def add_step(
        self,
        name: str,
        action: Callable[[Dict[str, Any]], Dict[str, Any]],
        compensation: Callable[[Dict[str, Any]], bool]
    ):
        self.steps.append(SagaStep(name, action, compensation))
        return self

    def execute(self, initial_context: Dict[str, Any]) -> SagaInstance:
        saga_id = str(uuid.uuid4())
        instance = SagaInstance(saga_id, self.steps)
        instance.context.update(initial_context)
        
        executed_steps: List[SagaStep] = []

        for index, step in enumerate(self.steps):
            instance.current_step_index = index
            try:
                result = step.action(instance.context)
                if result:
                    instance.context.update(result)
                    instance.step_results[step.name] = result
                instance.step_statuses[step.name] = StepStatus.SUCCESS
                executed_steps.append(step)
            except Exception as e:
                instance.step_statuses[step.name] = StepStatus.FAILED
                instance.status = SagaStatus.COMPENSATING
                self._rollback(instance, executed_steps)
                return instance

        instance.status = SagaStatus.SUCCESSFUL
        return instance

    def _rollback(self, instance: SagaInstance, executed_steps: List[SagaStep]):
        for step in reversed(executed_steps):
            try:
                success = step.compensation(instance.context)
                if success:
                    instance.step_statuses[step.name] = StepStatus.COMPENSATED
                else:
                    instance.step_statuses[step.name] = StepStatus.COMPENSATION_FAILED
            except Exception:
                instance.step_statuses[step.name] = StepStatus.COMPENSATION_FAILED

        has_compensation_failure = any(
            status == StepStatus.COMPENSATION_FAILED for status in instance.step_statuses.values()
        )
        if has_compensation_failure:
            instance.status = SagaStatus.FAILED
        else:
            instance.status = SagaStatus.COMPENSATED
