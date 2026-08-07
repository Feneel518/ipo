import asyncio
from collections.abc import Iterable

from app.scrapers.bse import BSEScraper, BSESMEScraper
from app.scrapers.models import NormalizationResult, SourceIssue
from app.scrapers.normalizer import IPONormalizer
from app.scrapers.nse import NSEEmergeScraper, NSEScraper


async def scrape_ipos(
    scrapers: Iterable[object] | None = None,
    *,
    normalizer: IPONormalizer | None = None,
) -> NormalizationResult:
    """Run all four official sources and return merged, upsert-ready IPOs."""

    issues = await fetch_ipo_issues(scrapers)
    return (normalizer or IPONormalizer()).merge(issues)


async def fetch_ipo_issues(
    scrapers: Iterable[object] | None = None,
) -> list[SourceIssue]:
    """Run all official sources while retaining their raw records."""

    active_scrapers = list(
        scrapers or (NSEScraper(), NSEEmergeScraper(), BSEScraper(), BSESMEScraper())
    )
    batches = await asyncio.gather(*(scraper.fetch() for scraper in active_scrapers))
    return [issue for batch in batches for issue in batch]
