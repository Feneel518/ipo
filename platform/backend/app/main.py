import time
import uuid
from collections import defaultdict, deque

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api import router
from app.config import get_settings
from app.db import engine

settings = get_settings()
app = FastAPI(
    title="IPO Dekho API",
    version="1.0.0",
    description="Read-only normalized NSE and BSE equity IPO data.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["GET"],
    allow_headers=["Accept", "Content-Type", "X-Request-ID"],
)
app.include_router(router)

_requests: dict[str, deque[float]] = defaultdict(deque)


@app.middleware("http")
async def request_controls(request: Request, call_next):
    request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
    client = request.client.host if request.client else "unknown"
    now = time.monotonic()
    window = _requests[client]
    while window and window[0] < now - 60:
        window.popleft()
    if len(window) >= 120:
        return JSONResponse({"detail": "Rate limit exceeded"}, status_code=429)
    window.append(now)
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    if request.method == "GET" and response.status_code == 200:
        response.headers["Cache-Control"] = "public, max-age=60, stale-while-revalidate=300"
    return response


@app.get("/health/live", tags=["health"])
def live() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready", tags=["health"])
def ready():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return {"status": "ready"}
    except Exception:
        return JSONResponse({"status": "unavailable"}, status_code=503)
