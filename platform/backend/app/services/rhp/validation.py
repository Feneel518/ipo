"""Deterministic semantic checks and canonical V1 metric normalization."""

import re
from dataclasses import dataclass
from decimal import Decimal

from app.services.rhp.schema import (
    FieldStatus,
    NumericFact,
    RhpExtractionV1,
    TextFact,
)

MONEY_UNITS = {"INR", "INR_LAKH", "INR_CRORE", "INR_MILLION"}


@dataclass(frozen=True)
class CanonicalMetric:
    metric: str
    financial_year: str | None
    numeric_value: Decimal | None
    text_value: str | None
    unit: str | None
    status: str
    provenance: list[dict] | None


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    severity: str
    field_path: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "severity": self.severity,
            "field_path": self.field_path,
            "message": self.message,
        }


def _issue(code: str, severity: str, name: str, message: str) -> ValidationIssue:
    return ValidationIssue(code, severity, name, message)


def _fact_issues(
    name: str,
    fact: NumericFact | TextFact,
    page_count: int,
    *,
    allow_negative: bool = True,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if fact.status == FieldStatus.FOUND and fact.value is None:
        issues.append(_issue("FOUND_WITHOUT_VALUE", "ERROR", name, "FOUND requires a value"))
    empty_statuses = {FieldStatus.NOT_FOUND, FieldStatus.NOT_APPLICABLE}
    if fact.status in empty_statuses and fact.value is not None:
        issues.append(
            _issue(
                "STATUS_VALUE_CONFLICT",
                "ERROR",
                name,
                f"{fact.status.value} must not contain a value",
            )
        )
    if isinstance(fact, NumericFact) and fact.status == FieldStatus.FOUND and fact.unit is None:
        issues.append(
            _issue("FOUND_WITHOUT_UNIT", "ERROR", name, "A found numeric value requires a unit")
        )
    if fact.status == FieldStatus.FOUND and not fact.sources:
        issues.append(
            _issue("FOUND_WITHOUT_SOURCE", "VERIFY", name, "Found fact has no provenance")
        )
    if (
        isinstance(fact, NumericFact)
        and fact.value is not None
        and not allow_negative
        and fact.value < 0
    ):
        issues.append(
            _issue("UNEXPECTED_NEGATIVE", "VERIFY", name, "Value is unexpectedly negative")
        )
    for source in fact.sources:
        if source.pdf_page is not None and source.pdf_page > page_count:
            issues.append(
                _issue(
                    "INVALID_PDF_PAGE",
                    "ERROR",
                    name,
                    f"Source page {source.pdf_page} exceeds PDF page count {page_count}",
                )
            )
        if fact.status == FieldStatus.FOUND and source.pdf_page is None:
            issues.append(
                _issue("SOURCE_PAGE_MISSING", "VERIFY", name, "Found source lacks pdf_page")
            )
        if fact.status == FieldStatus.FOUND and not source.evidence:
            issues.append(
                _issue("SOURCE_EVIDENCE_MISSING", "WARN", name, "Found source lacks evidence")
            )
    return issues


def _evidence_text(fact: NumericFact) -> str:
    return " ".join(source.evidence or "" for source in fact.sources)


def _evidence_numbers(evidence: str) -> list[Decimal]:
    """Parse ordinary RHP table numbers, including commas and accounting negatives."""
    values: list[Decimal] = []
    for match in re.finditer(r"(?<![\w.])(-?\(?\d[\d,]*(?:\.\d+)?\)?)(?![\w.])", evidence):
        token = match.group(1)
        negative = token.startswith("(") and token.endswith(")")
        token = token.strip("()").replace(",", "")
        try:
            value = Decimal(token)
        except Exception:
            continue
        values.append(-value if negative else value)
    return values


def _explicit_zero_pledge(evidence: str) -> bool:
    patterns = (
        r"\bnone\b.{0,160}\bpledge(?:d)?\b",
        r"\b(?:no|not)\b.{0,80}\bpledge(?:d)?\b",
        r"\b(?:have|has|are|is)\s+not\s+pledged?\b",
    )
    return any(re.search(pattern, evidence, flags=re.IGNORECASE) for pattern in patterns)


def _numeric_value_supported(name: str, fact: NumericFact) -> bool:
    if fact.status != FieldStatus.FOUND or fact.value is None:
        return True
    evidence = _evidence_text(fact)
    if name.endswith("pledged_shares_pct") and fact.value == 0:
        return fact.unit == "PERCENT" and _explicit_zero_pledge(evidence)
    expected = Decimal(str(fact.value))
    tolerance = max(Decimal("0.005"), abs(expected) * Decimal("0.000001"))
    return any(abs(candidate - expected) <= tolerance for candidate in _evidence_numbers(evidence))


def _borrowings_use_only_components(name: str, fact: NumericFact) -> bool:
    if not name.endswith("total_borrowings") or fact.status != FieldStatus.FOUND:
        return False
    evidence = _evidence_text(fact)
    component = re.search(
        r"\b(?:(?:long[ -]?term|short[ -]?term|non[ -]?current|current)\s+borrowings?"
        r"|aggregate\s+amount\s+of\s+loans?\s+guaranteed)\b",
        evidence,
        flags=re.IGNORECASE,
    )
    aggregate = re.search(
        r"\btotal\s+(?:borrowings?|debt|loans?|liabilities\s+from\s+financing\s+activities)\b",
        evidence,
        flags=re.IGNORECASE,
    )
    return bool(component and not aggregate)


def _named_facts(extraction: RhpExtractionV1):
    yield "company.industry", extraction.company.industry
    yield "company.business_description", extraction.company.business_description
    for index, fact in enumerate(extraction.company.competitive_strengths):
        yield f"company.competitive_strengths[{index}]", fact
    for index, fact in enumerate(extraction.company.growth_drivers):
        yield f"company.growth_drivers[{index}]", fact
    for period in extraction.financials:
        for name in (
            "revenue_from_operations",
            "profit_after_tax",
            "finance_cost",
            "operating_cash_flow",
            "trade_receivables",
            "total_borrowings",
            "total_equity",
        ):
            yield f"financials.{period.financial_year}.{name}", getattr(period, name)
    for name in ("pre_issue_holding_pct", "post_issue_holding_pct", "pledged_shares_pct"):
        yield f"promoters.{name}", getattr(extraction.promoters, name)
    for name in (
        "fresh_issue_amount",
        "offer_for_sale_amount",
        "total_issue_amount",
        "price_band_low",
        "price_band_high",
        "lot_size",
    ):
        yield f"ipo.{name}", getattr(extraction.ipo, name)
    for index, fact in enumerate(extraction.ipo.objects_of_issue):
        yield f"ipo.objects_of_issue[{index}]", fact
    for name in (
        "top_customer_revenue_pct",
        "top_5_customer_revenue_pct",
        "top_10_customer_revenue_pct",
        "commentary",
    ):
        yield f"customer_concentration.{name}", getattr(extraction.customer_concentration, name)
    for index, peer in enumerate(extraction.peers):
        yield f"peers[{index}].pe_reported_in_rhp", peer.pe_reported_in_rhp


def _expected_units(name: str) -> set[str] | None:
    metric = name.rsplit(".", 1)[-1]
    if metric in {
        "revenue_from_operations",
        "profit_after_tax",
        "finance_cost",
        "operating_cash_flow",
        "trade_receivables",
        "total_borrowings",
        "total_equity",
        "fresh_issue_amount",
        "offer_for_sale_amount",
        "total_issue_amount",
    }:
        return MONEY_UNITS
    if metric in {
        "pre_issue_holding_pct",
        "post_issue_holding_pct",
        "pledged_shares_pct",
        "top_customer_revenue_pct",
        "top_5_customer_revenue_pct",
        "top_10_customer_revenue_pct",
    }:
        return {"PERCENT"}
    if metric in {"price_band_low", "price_band_high"}:
        return {"INR"}
    if metric == "lot_size":
        return {"SHARES"}
    if metric == "pe_reported_in_rhp":
        return {"RATIO"}
    return None


def _comparable_found(*facts: NumericFact) -> bool:
    return all(
        fact.status == FieldStatus.FOUND
        and fact.value is not None
        and fact.unit is not None
        for fact in facts
    ) and len({fact.unit for fact in facts}) == 1


def validate_extraction(extraction: RhpExtractionV1, *, page_count: int) -> list[dict[str, str]]:
    issues: list[ValidationIssue] = []
    if not extraction.company.company_name:
        issues.append(
            _issue(
                "CRITICAL_FIELD_MISSING",
                "VERIFY",
                "company.company_name",
                "Company name is missing",
            )
        )
    periods = [period.financial_year for period in extraction.financials]
    if len(periods) != len(set(periods)):
        issues.append(
            _issue(
                "DUPLICATE_FINANCIAL_YEAR",
                "ERROR",
                "financials",
                "Duplicate financial-year labels",
            )
        )
    for name, fact in _named_facts(extraction):
        allow_negative = any(
            token in name
            for token in ("profit_after_tax", "operating_cash_flow")
        )
        issues.extend(
            _fact_issues(
                name,
                fact,
                page_count,
                allow_negative=allow_negative,
            )
        )
        if isinstance(fact, NumericFact) and not _numeric_value_supported(name, fact):
            issues.append(
                _issue(
                    "VALUE_NOT_IN_EVIDENCE",
                    "VERIFY",
                    name,
                    "FOUND numeric value is not supported by its cited evidence",
                )
            )
        expected_units = _expected_units(name)
        if (
            isinstance(fact, NumericFact)
            and fact.status == FieldStatus.FOUND
            and fact.unit is not None
            and expected_units is not None
            and fact.unit not in expected_units
        ):
            issues.append(
                _issue(
                    "INVALID_UNIT",
                    "ERROR",
                    name,
                    f"Expected one of {sorted(expected_units)}, got {fact.unit}",
                )
            )
        if isinstance(fact, NumericFact) and _borrowings_use_only_components(name, fact):
            issues.append(
                _issue(
                    "BORROWINGS_COMPONENT_ONLY",
                    "VERIFY",
                    name,
                    "Total borrowings must cite a reported aggregate, not a component "
                    "or contextual amount",
                )
            )
        if isinstance(fact, NumericFact) and fact.unit == "PERCENT" and fact.value is not None:
            if fact.value < 0 or fact.value > 100:
                issues.append(
                    _issue(
                        "PERCENT_OUT_OF_RANGE",
                        "ERROR",
                        name,
                        "Percentage is outside 0..100",
                    )
                )

    fresh = extraction.ipo.fresh_issue_amount
    ofs = extraction.ipo.offer_for_sale_amount
    total = extraction.ipo.total_issue_amount
    if all(fact.status == FieldStatus.FOUND for fact in (fresh, ofs, total)) and (
        fresh.unit == ofs.unit == total.unit and None not in (fresh.value, ofs.value, total.value)
    ):
        expected = float(fresh.value) + float(ofs.value)
        tolerance = max(abs(float(total.value)) * 0.01, 0.01)
        if abs(expected - float(total.value)) > tolerance:
            issues.append(
                _issue(
                    "ISSUE_AMOUNT_MISMATCH",
                    "VERIFY",
                    "ipo.total_issue_amount",
                    "Fresh issue + OFS does not match total",
                )
            )

    low = extraction.ipo.price_band_low
    high = extraction.ipo.price_band_high
    if _comparable_found(low, high) and float(low.value) > float(high.value):
        issues.append(
            _issue(
                "PRICE_BAND_REVERSED",
                "ERROR",
                "ipo.price_band_low",
                "Price band low exceeds price band high",
            )
        )

    pre = extraction.promoters.pre_issue_holding_pct
    post = extraction.promoters.post_issue_holding_pct
    if _comparable_found(pre, post) and float(post.value) > float(pre.value):
        issues.append(
            _issue(
                "PROMOTER_HOLDING_INCREASES_POST_ISSUE",
                "VERIFY",
                "promoters.post_issue_holding_pct",
                "Post-issue promoter holding exceeds pre-issue holding",
            )
        )

    concentration = extraction.customer_concentration
    concentration_facts = (
        ("top_customer_revenue_pct", concentration.top_customer_revenue_pct),
        ("top_5_customer_revenue_pct", concentration.top_5_customer_revenue_pct),
        ("top_10_customer_revenue_pct", concentration.top_10_customer_revenue_pct),
    )
    found_concentrations = [
        (name, fact)
        for name, fact in concentration_facts
        if fact.status == FieldStatus.FOUND and fact.value is not None
    ]
    for (left_name, left), (right_name, right) in zip(
        found_concentrations, found_concentrations[1:], strict=False
    ):
        if left.unit == right.unit == "PERCENT" and float(left.value) > float(right.value):
            issues.append(
                _issue(
                    "CUSTOMER_CONCENTRATION_ORDER",
                    "VERIFY",
                    f"customer_concentration.{right_name}",
                    f"{right_name} is lower than {left_name}",
                )
            )

    pledged = extraction.promoters.pledged_shares_pct
    pledged_evidence = " ".join(
        source.evidence or "" for source in pledged.sources
    )
    if pledged.status != FieldStatus.FOUND and _explicit_zero_pledge(pledged_evidence):
        issues.append(
            _issue(
                "EXPLICIT_ZERO_PLEDGE_MISSED",
                "VERIFY",
                "promoters.pledged_shares_pct",
                "Evidence explicitly says no promoter shares are pledged; expected FOUND 0 PERCENT",
            )
        )
    return [issue.as_dict() for issue in issues]


def _provenance(fact: NumericFact | TextFact) -> list[dict] | None:
    sources = [source.model_dump(mode="json") for source in fact.sources]
    return sources or None


def _numeric(
    metric: str,
    fact: NumericFact,
    financial_year: str | None = None,
    *,
    field_path: str | None = None,
    unsafe_paths: set[str] | None = None,
):
    supported = (
        _numeric_value_supported(field_path or metric, fact)
        and not _borrowings_use_only_components(field_path or metric, fact)
        and (field_path is None or field_path not in (unsafe_paths or set()))
    )
    if fact.status == FieldStatus.FOUND and not supported:
        return CanonicalMetric(
            metric=metric,
            financial_year=financial_year,
            numeric_value=None,
            text_value=None,
            unit=None,
            status=FieldStatus.AMBIGUOUS.value,
            provenance=_provenance(fact),
        )
    return CanonicalMetric(
        metric=metric,
        financial_year=financial_year,
        numeric_value=Decimal(str(fact.value)) if fact.value is not None else None,
        text_value=None,
        unit=fact.unit,
        status=fact.status.value,
        provenance=_provenance(fact),
    )


def _text(
    metric: str,
    fact: TextFact,
    *,
    field_path: str | None = None,
    unsafe_paths: set[str] | None = None,
):
    supported = field_path is None or field_path not in (unsafe_paths or set())
    if fact.status == FieldStatus.FOUND and not supported:
        return CanonicalMetric(
            metric=metric,
            financial_year=None,
            numeric_value=None,
            text_value=None,
            unit=None,
            status=FieldStatus.AMBIGUOUS.value,
            provenance=_provenance(fact),
        )
    return CanonicalMetric(
        metric=metric,
        financial_year=None,
        numeric_value=None,
        text_value=fact.value,
        unit=None,
        status=fact.status.value,
        provenance=_provenance(fact),
    )


def normalize_extraction(
    extraction: RhpExtractionV1,
    *,
    issues: list[dict[str, str]] | None = None,
) -> list[CanonicalMetric]:
    """Build canonical rows while quarantining any disputed numeric fact.

    Missing facts remain NOT_FOUND. A value with an ERROR or VERIFY issue keeps
    its provenance but is stored as AMBIGUOUS with no value or unit, ensuring a
    model-produced number cannot become canonical before review/correction.
    """
    unsafe_paths = {
        issue["field_path"]
        for issue in (issues or [])
        if issue.get("severity") in {"ERROR", "VERIFY"}
    }
    metrics = [
        CanonicalMetric(
            metric="company_name",
            financial_year=None,
            numeric_value=None,
            text_value=extraction.company.company_name,
            unit=None,
            status="FOUND" if extraction.company.company_name else "NOT_FOUND",
            provenance=None,
        ),
        _text(
            "industry",
            extraction.company.industry,
            field_path="company.industry",
            unsafe_paths=unsafe_paths,
        ),
        _text(
            "business_description",
            extraction.company.business_description,
            field_path="company.business_description",
            unsafe_paths=unsafe_paths,
        ),
    ]
    for period in extraction.financials:
        for name in (
            "revenue_from_operations",
            "profit_after_tax",
            "finance_cost",
            "operating_cash_flow",
            "trade_receivables",
            "total_borrowings",
            "total_equity",
        ):
            path = f"financials.{period.financial_year}.{name}"
            metrics.append(
                _numeric(
                    name,
                    getattr(period, name),
                    period.financial_year,
                    field_path=path,
                    unsafe_paths=unsafe_paths,
                )
            )
    for name in ("pre_issue_holding_pct", "post_issue_holding_pct", "pledged_shares_pct"):
        metrics.append(
            _numeric(
                name,
                getattr(extraction.promoters, name),
                field_path=f"promoters.{name}",
                unsafe_paths=unsafe_paths,
            )
        )
    for name in (
        "fresh_issue_amount",
        "offer_for_sale_amount",
        "total_issue_amount",
        "price_band_low",
        "price_band_high",
        "lot_size",
    ):
        metrics.append(
            _numeric(
                name,
                getattr(extraction.ipo, name),
                field_path=f"ipo.{name}",
                unsafe_paths=unsafe_paths,
            )
        )
    for name in (
        "top_customer_revenue_pct",
        "top_5_customer_revenue_pct",
        "top_10_customer_revenue_pct",
    ):
        metrics.append(
            _numeric(
                name,
                getattr(extraction.customer_concentration, name),
                field_path=f"customer_concentration.{name}",
                unsafe_paths=unsafe_paths,
            )
        )
    return metrics
