from decimal import Decimal

from app.services.rhp.calculations import calculate_metrics
from app.services.rhp.validation import CanonicalMetric


def reported(metric: str, year: str, value: str | None) -> CanonicalMetric:
    return CanonicalMetric(
        metric=metric,
        financial_year=year,
        numeric_value=Decimal(value) if value is not None else None,
        text_value=None,
        unit="INR_CRORE" if value is not None else None,
        status="FOUND" if value is not None else "NOT_FOUND",
        provenance=None,
    )


def financial_period(
    year: str,
    *,
    revenue: str,
    pat: str,
    ocf: str,
    receivables: str,
    debt: str,
    equity: str,
) -> list[CanonicalMetric]:
    return [
        reported("revenue_from_operations", year, revenue),
        reported("profit_after_tax", year, pat),
        reported("operating_cash_flow", year, ocf),
        reported("trade_receivables", year, receivables),
        reported("total_borrowings", year, debt),
        reported("total_equity", year, equity),
    ]


def by_name(metrics: list[CanonicalMetric], metric: str, year: str) -> CanonicalMetric:
    return next(
        item
        for item in metrics
        if item.metric == metric and item.financial_year == year
    )


def test_calculates_all_v2_metrics_from_reported_financials():
    facts = [
        *financial_period(
            "FY2024",
            revenue="100",
            pat="10",
            ocf="8",
            receivables="20",
            debt="30",
            equity="60",
        ),
        *financial_period(
            "FY2025",
            revenue="150",
            pat="15",
            ocf="18",
            receivables="24",
            debt="20",
            equity="80",
        ),
        *financial_period(
            "FY2026",
            revenue="225",
            pat="22.5",
            ocf="27",
            receivables="27",
            debt="10",
            equity="100",
        ),
    ]

    metrics = calculate_metrics(facts)

    assert by_name(metrics, "pat_margin", "FY2026").numeric_value == Decimal("10.000000")
    assert by_name(metrics, "debt_to_equity", "FY2026").numeric_value == Decimal("0.100000")
    assert by_name(metrics, "cash_conversion", "FY2026").numeric_value == Decimal("1.200000")
    assert by_name(metrics, "receivables_to_revenue", "FY2026").numeric_value == Decimal(
        "0.120000"
    )
    assert by_name(metrics, "revenue_growth", "FY2026").numeric_value == Decimal("50.000000")
    assert by_name(metrics, "receivable_trend", "FY2026").numeric_value == Decimal(
        "-25.000000"
    )
    assert by_name(metrics, "sales_cagr", "FY2024-FY2026").numeric_value == Decimal(
        "50.000000"
    )
    assert by_name(metrics, "pat_cagr", "FY2024-FY2026").numeric_value == Decimal(
        "50.000000"
    )
    assert all(metric.source == "CALCULATED" for metric in metrics)


def test_pat_cagr_is_not_forced_when_starting_pat_is_non_positive():
    facts = [
        *financial_period(
            "Fiscal 2024",
            revenue="100",
            pat="-2",
            ocf="1",
            receivables="10",
            debt="5",
            equity="20",
        ),
        *financial_period(
            "Fiscal 2026",
            revenue="121",
            pat="10",
            ocf="9",
            receivables="11",
            debt="4",
            equity="25",
        ),
    ]

    pat_cagr = by_name(calculate_metrics(facts), "pat_cagr", "FY2024-FY2026")

    assert pat_cagr.numeric_value is None
    assert pat_cagr.status == "NOT_APPLICABLE"
    assert pat_cagr.text_value == "START_VALUE_NON_POSITIVE"


def test_calculations_do_not_use_quarantined_or_missing_facts():
    facts = financial_period(
        "FY2026",
        revenue="100",
        pat="10",
        ocf="8",
        receivables="20",
        debt="30",
        equity="60",
    )
    facts[0] = CanonicalMetric(
        metric="revenue_from_operations",
        financial_year="FY2026",
        numeric_value=None,
        text_value=None,
        unit=None,
        status="AMBIGUOUS",
        provenance=None,
    )

    metrics = calculate_metrics(facts)

    margin = by_name(metrics, "pat_margin", "FY2026")
    assert margin.numeric_value is None
    assert margin.status == "AMBIGUOUS"
    assert margin.text_value == "REQUIRED_INPUT_AMBIGUOUS"
