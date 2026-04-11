from app.db import SessionLocal
from app.models import Project, TaskStatus
from app.services.task_manager import create_task, heartbeat, mark_stale_if_needed, recover_stale_task, transition_task


def test_task_state_transitions_and_recovery() -> None:
    db = SessionLocal()
    try:
        project = Project(tenant_id="t1", name="Test", niche_tags=[])
        db.add(project)
        db.commit()
        db.refresh(project)

        task = create_task(
            db,
            project_id=project.id,
            task_type="campaign_generate",
            owner_agent="SupervisorAgent",
            idempotency_key="k1",
            stale_timeout_seconds=1,
            max_retries=2,
        )
        transition_task(db, task, TaskStatus.running)
        heartbeat(db, task)

        # force stale
        task.last_heartbeat_at = task.last_heartbeat_at.replace(year=2000)
        db.add(task)
        db.commit()

        stale = mark_stale_if_needed(db, task)
        assert stale.status == TaskStatus.stale.value

        recovered = recover_stale_task(db, stale)
        assert recovered.status == TaskStatus.running.value
        assert recovered.retries == 1
    finally:
        db.close()
