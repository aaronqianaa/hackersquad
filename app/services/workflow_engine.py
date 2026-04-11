from collections.abc import Callable
from threading import Thread


class WorkflowEngine:
    def run_async(self, fn: Callable[[], None]) -> None:
        raise NotImplementedError


class LocalThreadWorkflowEngine(WorkflowEngine):
    def run_async(self, fn: Callable[[], None]) -> None:
        thread = Thread(target=fn, daemon=True)
        thread.start()


class TemporalWorkflowEngine(WorkflowEngine):
    """
    Placeholder adapter for Temporal integration.
    In production, register workflows/activities and dispatch by task id.
    """

    def __init__(self) -> None:
        self._fallback = LocalThreadWorkflowEngine()

    def run_async(self, fn: Callable[[], None]) -> None:
        self._fallback.run_async(fn)
