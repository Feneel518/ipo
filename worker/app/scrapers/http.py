from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/138.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}


@asynccontextmanager
async def exchange_client(
    client: httpx.AsyncClient | None,
    *,
    headers: dict[str, str],
) -> AsyncIterator[httpx.AsyncClient]:
    if client is not None:
        yield client
        return

    async with httpx.AsyncClient(
        headers=headers,
        follow_redirects=True,
        timeout=httpx.Timeout(30.0, connect=10.0),
    ) as owned_client:
        yield owned_client
