from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Checkpoint, Task, TaskStatus


VALID_TRANSITIONS = {
    TaskStatus.queued.value: {TaskStatus.running.value, TaskStatus.cancelled.value, TaskStatus.failed.value},
    TaskStatus.running.value: {
        TaskStatus.completed.value,
        TaskStatus.failed.value,
        TaskStatus.blocked.value,
        TaskStatus.stale.value,
        TaskStatus.cancelled.value,
    },
    TaskStatus.stale.value: {TaskStatus.running.value, TaskStatus.failed.value, TaskStatus.blocked.value},
    TaskStatus.blocked.value: {TaskStatus.running.value, TaskStatus.failed.value, TaskStatus.cancelled.value},
    TaskStatus.completed.value: set(),
    TaskStatus.failed.value: set(),
    TaskStatus.cancelled.value: set(),
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def transition_task(db: Session, task: Task, to_status: TaskStatus, reason: str | None = None) -> Task:
    if to_status.value not in VALID_TRANSITIONS.get(task.status, set()):
        raise ValueError(f"Invalid task transition: {task.status} -> {to_status.value}")
    task.status = to_status.value
    if reason:
        task.error_reason = reason
    task.updated_at = utcnow()
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def heartbeat(db: Session, task: Task) -> Task:
    task.last_heartbeat_at = utcnow()
    task.updated_at = task.last_heartbeat_at
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def save_checkpoint(db: Session, task: Task, step: str, payload: dict) -> Checkpoint:
    task.checkpoint = step
    task.updated_at = utcnow()
    cp = Checkpoint(task_id=task.id, step=step, payload=payload)
    db.add(task)
    db.add(cp)
    db.commit()
    db.refresh(task)
    db.refresh(cp)
    return cp


def heartbeat_age_seconds(task: Task) -> int | None:
    if not task.last_heartbeat_at:
        return None
    return int((utcnow() - _as_aware(task.last_heartbeat_at)).total_seconds())


def mark_stale_if_needed(db: Session, task: Task) -> Task:
    age = heartbeat_age_seconds(task)
    if task.status == TaskStatus.running.value and age is not None and age > task.stale_timeout_seconds:
        task.status = TaskStatus.stale.value
        task.error_reason = "Heartbeat timeout; worker considered stale"
        task.updated_at = utcnow()
        db.add(task)
        db.commit()
        db.refresh(task)
    return task


def recover_stale_task(db: Session, task: Task) -> Task:
    if task.status != TaskStatus.stale.value:
        return task

    if task.retries >= task.max_retries:
        task.status = TaskStatus.blocked.value
        task.error_reason = "Retry limit reached after stale detection"
        task.updated_at = utcnow()
        db.add(task)
        db.commit()
        db.refresh(task)
        return task

    task.retries += 1
    task.status = TaskStatus.running.value
    task.error_reason = "Recovered from stale state"
    task.last_heartbeat_at = utcnow()
    task.updated_at = task.last_heartbeat_at
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def create_task(
    db: Session,
    project_id: str,
    task_type: str,
    owner_agent: str,
    idempotency_key: str,
    stale_timeout_seconds: int | None = None,
    max_retries: int | None = None,
) -> Task:
    task = Task(
        project_id=project_id,
        task_type=task_type,
        owner_agent=owner_agent,
        idempotency_key=idempotency_key,
        stale_timeout_seconds=stale_timeout_seconds or settings.stale_timeout_seconds,
        max_retries=max_retries or settings.max_retries,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task
