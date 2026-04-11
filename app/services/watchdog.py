import time
from threading import Event, Thread

from sqlalchemy.orm import sessionmaker

from app.services.supervisor import SupervisorAgent


class WatchdogRunner:
    def __init__(self, session_factory: sessionmaker, supervisor: SupervisorAgent, interval_seconds: int = 10) -> None:
        self.session_factory = session_factory
        self.supervisor = supervisor
        self.interval_seconds = interval_seconds
        self._stop = Event()
        self._thread: Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return

        def _run() -> None:
            while not self._stop.is_set():
                db = self.session_factory()
                try:
                    self.supervisor.watchdog_scan(db)
                finally:
                    db.close()
                time.sleep(self.interval_seconds)

        self._thread = Thread(target=_run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
