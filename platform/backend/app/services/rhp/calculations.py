"""Deterministic investor metrics calculated from validated RHP facts.

Percent values use percentage units (10 means 10%). Receivable trend is the
year-on-year percentage change in the receivables/revenue ratio. Debt excludes
lease liabilities unless the RHP's reported total-borrowings fact includes them.
"""

import re
from collections.abc import Callable
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from app.services.rhp.validation import CanonicalMetric

SIX_PLACES = Decimal("0.000001")


def _rounded(value: Decimal) -> Decimal:
    return value.quantize(SIX_PLACES, rounding=ROUND_HALF_UP)


def _year_end(label: str) -> int | None:
    """Return the terminal year from common RHP financial-period labels."""
    short_range = re.search(r"(?<!\d)((?:19|20)\d{2})\s*[-/]\s*(\d{2})(?!\d)", label)
    if short_range:
        start = int(short_range.group(1))
        short_end = int(short_range.group(2))
        end = start // 100 * 100 + short_end
        return end + 100 if end < start else end
    years = [int(value) for value in re.findall(r"(?<!\d)((?:19|20)\d{2})(?!\d)", label)]
    return max(years) if years else None


def _input_ref(metric: CanonicalMetric) -> dict[str, str | None]:
    return {"source_metric": metric.metric, "financial_year": metric.financial_year}


def _result(
    metric: str,
    financial_year: str | None,
    unit: str,
    inputs: list[CanonicalMetric],
    *,
    value: Decimal | None = None,
    reason: str | None = None,
    status: str = "NOT_APPLICABLE",
) -> CanonicalMetric:
    return CanonicalMetric(
        metric=metric,
        financial_year=financial_year,
        numeric_value=_rounded(value) if value is not None else None,
        text_value=reason,
        unit=unit,
        status="FOUND" if value is not None else status,
        provenance=[_input_ref(item) for item in inputs] or None,
        source="CALCULATED",
    )


def _ratio(
    metric: str,
    numerator: CanonicalMetric | None,
    denominator: CanonicalMetric | None,
    financial_year: str,
    *,
    multiplier: Decimal = Decimal("1"),
    zero_reason: str = "DENOMINATOR_ZERO",
) -> CanonicalMetric:
    inputs = [item for item in (numerator, denominator) if item is not None]
    if any(item.status == "AMBIGUOUS" for item in inputs):
        return _result(
            metric,
            financial_year,
            "PERCENT" if multiplier == 100 else "RATIO",
            inputs,
            reason="REQUIRED_INPUT_AMBIGUOUS",
            status="AMBIGUOUS",
        )
    if (
        numerator is None
        or denominator is None
        or numerator.status != "FOUND"
        or denominator.status != "FOUND"
        or numerator.numeric_value is None
        or denominator.numeric_value is None
    ):
        return _result(
            metric,
            financial_year,
            "PERCENT" if multiplier == 100 else "RATIO",
            inputs,
            reason="REQUIRED_INPUT_NOT_FOUND",
            status="NOT_FOUND",
        )
    if denominator.numeric_value == 0:
        return _result(
            metric,
            financial_year,
            "PERCENT" if multiplier == 100 else "RATIO",
            inputs,
            reason=zero_reason,
        )
    return _result(
        metric,
        financial_year,
        "PERCENT" if multiplier == 100 else "RATIO",
        inputs,
        value=numerator.numeric_value / denominator.numeric_value * multiplier,
    )


def _growth(
    metric: str,
    start: CanonicalMetric | None,
    end: CanonicalMetric | None,
    financial_year: str,
    transform: Callable[[Decimal, Decimal], Decimal],
    *,
    unit: str = "PERCENT",
) -> CanonicalMetric:
    inputs = [item for item in (start, end) if item is not None]
    if any(item.status == "AMBIGUOUS" for item in inputs):
        return _result(
            metric,
            financial_year,
            unit,
            inputs,
            reason="REQUIRED_INPUT_AMBIGUOUS",
            status="AMBIGUOUS",
        )
    if (
        start is None
        or end is None
        or start.status != "FOUND"
        or end.status != "FOUND"
        or start.numeric_value is None
        or end.numeric_value is None
    ):
        return _result(
            metric,
            financial_year,
            unit,
            inputs,
            reason="REQUIRED_INPUT_NOT_FOUND",
            status="NOT_FOUND",
        )
    if start.numeric_value <= 0:
        return _result(metric, financial_year, unit, inputs, reason="START_VALUE_NON_POSITIVE")
    return _result(
        metric,
        financial_year,
        unit,
        inputs,
        value=transform(start.numeric_value, end.numeric_value),
    )


def _cagr(
    metric: str,
    start: CanonicalMetric | None,
    end: CanonicalMetric | None,
    periods: int,
    label: str | None,
) -> CanonicalMetric:
    inputs = [item for item in (start, end) if item is not None]
    if periods <= 0:
        return _result(metric, label, "PERCENT", inputs, reason="INSUFFICIENT_PERIODS")
    if (
        start is None
        or end is None
        or start.status != "FOUND"
        or end.status != "FOUND"
        or start.numeric_value is None
        or end.numeric_value is None
    ):
        if any(item.status == "AMBIGUOUS" for item in inputs):
            return _result(
                metric,
                label,
                "PERCENT",
                inputs,
                reason="REQUIRED_INPUT_AMBIGUOUS",
                status="AMBIGUOUS",
            )
        return _result(
            metric,
            label,
            "PERCENT",
            inputs,
            reason="REQUIRED_INPUT_NOT_FOUND",
            status="NOT_FOUND",
        )
    if start.numeric_value <= 0:
        return _result(metric, label, "PERCENT", inputs, reason="START_VALUE_NON_POSITIVE")
    if end.numeric_value < 0:
        return _result(metric, label, "PERCENT", inputs, reason="END_VALUE_NEGATIVE")
    try:
        growth = float(end.numeric_value / start.numeric_value) ** (1 / periods) - 1
        value = Decimal(str(growth * 100))
    except (InvalidOperation, OverflowError, ValueError):
        return _result(metric, label, "PERCENT", inputs, reason="CALCULATION_UNDEFINED")
    return _result(metric, label, "PERCENT", inputs, value=value)


def calculate_metrics(reported: list[CanonicalMetric]) -> list[CanonicalMetric]:
    """Calculate v2 metrics without using missing or quarantined Gemini values."""
    financial = [item for item in reported if item.financial_year is not None]
    by_key = {(item.metric, item.financial_year): item for item in financial}
    labels = list(dict.fromkeys(item.financial_year for item in financial if item.financial_year))
    calculated: list[CanonicalMetric] = []

    for label in labels:
        revenue = by_key.get(("revenue_from_operations", label))
        pat = by_key.get(("profit_after_tax", label))
        calculated.extend(
            [
                _ratio("pat_margin", pat, revenue, label, multiplier=Decimal("100")),
                _ratio(
                    "debt_to_equity",
                    by_key.get(("total_borrowings", label)),
                    by_key.get(("total_equity", label)),
                    label,
                ),
                _ratio(
                    "cash_conversion",
                    by_key.get(("operating_cash_flow", label)),
                    pat,
                    label,
                ),
                _ratio(
                    "receivables_to_revenue",
                    by_key.get(("trade_receivables", label)),
                    revenue,
                    label,
                ),
            ]
        )

    ordered = sorted(
        ((year, label) for label in labels if (year := _year_end(label)) is not None),
        key=lambda item: item[0],
    )
    if len({year for year, _ in ordered}) != len(ordered):
        ordered = []
    for (previous_year, previous), (current_year, current) in zip(
        ordered, ordered[1:], strict=False
    ):
        previous_revenue = by_key.get(("revenue_from_operations", previous))
        current_revenue = by_key.get(("revenue_from_operations", current))
        if current_year - previous_year != 1:
            calculated.extend(
                [
                    _result(
                        "revenue_growth",
                        current,
                        "PERCENT",
                        [item for item in (previous_revenue, current_revenue) if item],
                        reason="NON_CONSECUTIVE_PERIODS",
                    ),
                    _result(
                        "receivable_trend",
                        current,
                        "PERCENT",
                        [],
                        reason="NON_CONSECUTIVE_PERIODS",
                    ),
                ]
            )
            continue
        calculated.append(
            _growth(
                "revenue_growth",
                previous_revenue,
                current_revenue,
                current,
                lambda start, end: (end / start - 1) * 100,
            )
        )
        previous_ratio = next(
            (
                item
                for item in calculated
                if item.metric == "receivables_to_revenue"
                and item.financial_year == previous
            ),
            None,
        )
        current_ratio = next(
            (
                item
                for item in calculated
                if item.metric == "receivables_to_revenue"
                and item.financial_year == current
            ),
            None,
        )
        calculated.append(
            _growth(
                "receivable_trend",
                previous_ratio,
                current_ratio,
                current,
                lambda start, end: (end / start - 1) * 100,
            )
        )

    if len(ordered) >= 2:
        start_year, start_label = ordered[0]
        end_year, end_label = ordered[-1]
        span_label = f"FY{start_year}-FY{end_year}"
        periods = end_year - start_year
        calculated.extend(
            [
                _cagr(
                    "sales_cagr",
                    by_key.get(("revenue_from_operations", start_label)),
                    by_key.get(("revenue_from_operations", end_label)),
                    periods,
                    span_label,
                ),
                _cagr(
                    "pat_cagr",
                    by_key.get(("profit_after_tax", start_label)),
                    by_key.get(("profit_after_tax", end_label)),
                    periods,
                    span_label,
                ),
            ]
        )
    else:
        calculated.extend(
            [
                _cagr("sales_cagr", None, None, 0, None),
                _cagr("pat_cagr", None, None, 0, None),
            ]
        )
    return calculated
