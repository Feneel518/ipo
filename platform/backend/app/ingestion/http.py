from contextlib import asynccontextmanager

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential_jitter

from app.config import get_settings

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0 Safari/537.36"
    ),
    "Accept-Language": "en-IN,en;q=0.9",
}


@asynccontextmanager
async def source_client():
    settings = get_settings()
    async with httpx.AsyncClient(
        timeout=settings.request_timeout_seconds,
        follow_redirects=True,
        headers=BROWSER_HEADERS,
        limits=httpx.Limits(max_connections=6, max_keepalive_connections=3),
    ) as client:
        yield client


def _retryable_source_error(exc: BaseException) -> bool:
    if isinstance(exc, (httpx.TimeoutException, httpx.NetworkError)):
        return True
    return isinstance(exc, httpx.HTTPStatusError) and (
        exc.response.status_code == 429 or exc.response.status_code >= 500
    )


@retry(
    retry=retry_if_exception(_retryable_source_error),
    stop=stop_after_attempt(3),
    wait=wait_exponential_jitter(initial=1, max=8),
    reraise=True,
)
async def get_json(client: httpx.AsyncClient, url: str, **kwargs):
    response = await client.get(url, **kwargs)
    response.raise_for_status()
    return response.json()
