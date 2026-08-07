import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, status
from fastapi.responses import JSONResponse

from app.config import Settings, get_settings
from app.scheduler import create_worker_scheduler

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        logger.info("worker starting", extra={"environment": settings.app_env})
        worker_scheduler = create_worker_scheduler(settings)
        app.state.worker_scheduler = worker_scheduler
        if worker_scheduler is None:
            logger.warning("scheduler disabled or DATABASE_URL is not configured")
        else:
            worker_scheduler.start()
            logger.info("scheduler started timezone=Asia/Kolkata")
        try:
            yield
        finally:
            if worker_scheduler is not None:
                worker_scheduler.shutdown()
            logger.info("worker stopping")

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None,
        lifespan=lifespan,
    )

    @app.get("/health/live", tags=["health"])
    async def liveness() -> dict[str, str]:
        """Confirm that the process is running."""

        return {"status": "ok", "service": settings.app_name}

    @app.get("/health/ready", tags=["health"])
    async def readiness() -> JSONResponse:
        """Confirm that required runtime configuration is available."""

        database_configured = settings.database_url is not None
        return JSONResponse(
            status_code=(
                status.HTTP_200_OK
                if database_configured
                else status.HTTP_503_SERVICE_UNAVAILABLE
            ),
            content={
                "status": "ready" if database_configured else "not_ready",
                "checks": {"database_configured": database_configured},
            },
        )

    return app


app = create_app()
