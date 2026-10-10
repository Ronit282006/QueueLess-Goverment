"""QueueLess Government Office API — application factory."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import admin, analytics, auth, catalog, incidents, queue, staff, staff_management, system, tokens, ws
from .api.staff_management import counters_router
from .config import get_settings
from .db import Base, engine
from .errors import install as install_errors
from .realtime import redis_listener
from .worker import email_worker_loop, sweeper_loop

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    # Alembic owns schema migrations; create_all keeps fresh dev/test databases
    # bootstrapped without extra steps and is a no-op once migrations have run.
    Base.metadata.create_all(engine)
    background = [asyncio.create_task(redis_listener())]
    if settings.background_workers_enabled:
        background.append(asyncio.create_task(email_worker_loop(poll_seconds=settings.email_poll_sec)))
        background.append(asyncio.create_task(sweeper_loop(interval_seconds=settings.sweeper_interval_sec)))
    try:
        yield
    finally:
        for task in background:
            task.cancel()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="1.0.0",
        description=(
            "AI-powered, real-time, fair and scalable queue operating system for "
            "government offices. Predict → Monitor → Optimize → Notify → Learn."
        ),
        lifespan=lifespan,
    )
    install_errors(app)

    for module in (system, auth, catalog, queue, tokens, incidents, staff, admin, analytics, staff_management, ws):
        app.include_router(module.router)
    app.include_router(counters_router)

    # Keep CORS outside FastAPI's server-error middleware so even unexpected
    # 500 responses carry CORS headers and the browser can show the real error.
    return CORSMiddleware(
        app,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID", "X-Response-Time-Ms"],
    )


app = create_app()
