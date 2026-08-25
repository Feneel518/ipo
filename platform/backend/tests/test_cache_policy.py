from app.main import _cache_control


def test_ipo_list_and_detail_responses_cannot_be_cached_independently():
    assert _cache_control("/api/v1/ipos") == "no-store"
    assert _cache_control("/api/v1/ipos/tempsens-instruments-india-limited") == "no-store"


def test_non_api_health_response_keeps_short_cache_policy():
    assert _cache_control("/health/live") == "public, max-age=60, stale-while-revalidate=300"
