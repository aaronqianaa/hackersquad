from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import router, supervisor
from app.core.config import settings
from app.db import Base, SessionLocal, engine
from app.services.watchdog import WatchdogRunner


watchdog = WatchdogRunner(SessionLocal, supervisor, interval_seconds=10)


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    watchdog.start()
    yield
    watchdog.stop()


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.include_router(router, prefix=settings.api_prefix)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
