"""Versioned structured output contract for the first RHP extraction pass."""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = "rhp-v1.1"


class ExtractionModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FieldStatus(StrEnum):
    FOUND = "FOUND"
    NOT_FOUND = "NOT_FOUND"
    AMBIGUOUS = "AMBIGUOUS"
    CONFLICTING = "CONFLICTING"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class EvidenceRef(ExtractionModel):
    pdf_page: int | None = Field(default=None, ge=1)
    document_page_label: str | None = Field(default=None, max_length=40)
    evidence: str | None = Field(default=None, max_length=400)


class NumericFact(ExtractionModel):
    value: float | None = None
    unit: Literal[
        "INR",
        "INR_LAKH",
        "INR_CRORE",
        "INR_MILLION",
        "PERCENT",
        "RATIO",
        "SHARES",
        "OTHER",
    ] | None = None
    status: FieldStatus
    sources: list[EvidenceRef] = Field(default_factory=list, max_length=3)


class TextFact(ExtractionModel):
    value: str | None = Field(default=None, max_length=1500)
    status: FieldStatus
    sources: list[EvidenceRef] = Field(default_factory=list, max_length=3)


class FinancialPeriod(ExtractionModel):
    financial_year: str = Field(
        max_length=20,
        description="Use the financial-year label printed in the RHP.",
    )
    revenue_from_operations: NumericFact
    profit_after_tax: NumericFact
    finance_cost: NumericFact
    operating_cash_flow: NumericFact
    trade_receivables: NumericFact
    total_borrowings: NumericFact
    total_equity: NumericFact


class CompanySection(ExtractionModel):
    company_name: str | None = Field(default=None, max_length=300)
    industry: TextFact
    business_description: TextFact
    products_services: list[str] = Field(default_factory=list, max_length=20)
    competitive_strengths: list[TextFact] = Field(default_factory=list, max_length=10)
    growth_drivers: list[TextFact] = Field(default_factory=list, max_length=10)


class PromoterSection(ExtractionModel):
    names: list[str] = Field(default_factory=list, max_length=20)
    pre_issue_holding_pct: NumericFact
    post_issue_holding_pct: NumericFact
    pledged_shares_pct: NumericFact


class IpoSection(ExtractionModel):
    fresh_issue_amount: NumericFact
    offer_for_sale_amount: NumericFact
    total_issue_amount: NumericFact
    price_band_low: NumericFact
    price_band_high: NumericFact
    lot_size: NumericFact
    objects_of_issue: list[TextFact] = Field(default_factory=list, max_length=10)


class CustomerConcentration(ExtractionModel):
    top_customer_revenue_pct: NumericFact
    top_5_customer_revenue_pct: NumericFact
    top_10_customer_revenue_pct: NumericFact
    commentary: TextFact


class Peer(ExtractionModel):
    name: str = Field(max_length=300)
    pe_reported_in_rhp: NumericFact


class RiskItem(ExtractionModel):
    title: str = Field(max_length=300)
    category: Literal[
        "CUSTOMER",
        "SUPPLIER",
        "DEBT",
        "WORKING_CAPITAL",
        "REGULATORY",
        "LITIGATION",
        "PROMOTER",
        "RELATED_PARTY",
        "OPERATIONS",
        "GEOGRAPHY",
        "OTHER",
    ]
    description: str = Field(max_length=1200)
    sources: list[EvidenceRef] = Field(default_factory=list, max_length=3)


class ExtractionWarnings(ExtractionModel):
    warnings: list[str] = Field(default_factory=list, max_length=30)
    conflicts: list[str] = Field(default_factory=list, max_length=30)


class RhpExtractionV1(ExtractionModel):
    """Compact V1 facts; calculated and live-market fields are intentionally excluded."""

    company: CompanySection
    financials: list[FinancialPeriod] = Field(min_length=1, max_length=4)
    promoters: PromoterSection
    ipo: IpoSection
    customer_concentration: CustomerConcentration
    peers: list[Peer] = Field(default_factory=list, max_length=15)
    risks: list[RiskItem] = Field(default_factory=list, max_length=15)
    extraction_meta: ExtractionWarnings


class CompanyExtractionPass(ExtractionModel):
    company: CompanySection


class FinancialExtractionPass(ExtractionModel):
    financials: list[FinancialPeriod] = Field(min_length=1, max_length=4)


class OfferExtractionPass(ExtractionModel):
    promoters: PromoterSection
    ipo: IpoSection
    customer_concentration: CustomerConcentration
    peers: list[Peer] = Field(default_factory=list, max_length=15)


class RiskExtractionPass(ExtractionModel):
    risks: list[RiskItem] = Field(default_factory=list, max_length=15)
    extraction_meta: ExtractionWarnings
