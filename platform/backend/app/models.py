from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Lifecycle(StrEnum):
    UPCOMING = "UPCOMING"
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    LISTED = "LISTED"
    WITHDRAWN = "WITHDRAWN"
    CANCELLED = "CANCELLED"


class Exchange(StrEnum):
    NSE = "NSE"
    BSE = "BSE"


class Segment(StrEnum):
    MAINBOARD = "MAINBOARD"
    SME = "SME"


class MarketType(StrEnum):
    BOOK_BUILT = "BOOK_BUILT"
    FIXED_PRICE = "FIXED_PRICE"
    UNKNOWN = "UNKNOWN"


class Ipo(Base):
    __tablename__ = "ipos"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    company_name: Mapped[str] = mapped_column(String(300), index=True)
    normalized_name: Mapped[str] = mapped_column(String(300), index=True)
    slug: Mapped[str] = mapped_column(String(340), unique=True, index=True)
    isin: Mapped[str | None] = mapped_column(String(20), unique=True, nullable=True)
    lifecycle: Mapped[Lifecycle] = mapped_column(Enum(Lifecycle, name="ipo_lifecycle"), index=True)
    issue_type: Mapped[str] = mapped_column(String(40), default="IPO")
    market_type: Mapped[MarketType] = mapped_column(
        Enum(MarketType, name="ipo_market_type"), default=MarketType.UNKNOWN
    )
    open_date: Mapped[date | None] = mapped_column(Date, index=True)
    close_date: Mapped[date | None] = mapped_column(Date, index=True)
    allotment_date: Mapped[date | None] = mapped_column(Date, index=True)
    allotment_date_is_estimated: Mapped[bool] = mapped_column(Boolean, default=False)
    refund_date: Mapped[date | None] = mapped_column(Date, index=True)
    refund_date_is_estimated: Mapped[bool] = mapped_column(Boolean, default=False)
    credit_date: Mapped[date | None] = mapped_column(Date, index=True)
    credit_date_is_estimated: Mapped[bool] = mapped_column(Boolean, default=False)
    expected_listing_date: Mapped[date | None] = mapped_column(Date, index=True)
    listing_date: Mapped[date | None] = mapped_column(Date, index=True)
    price_low: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    price_high: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    final_issue_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    face_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    tick_size: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    lot_size: Mapped[int | None] = mapped_column(BigInteger)
    minimum_bid_quantity: Mapped[int | None] = mapped_column(BigInteger)
    minimum_retail_investment: Mapped[Decimal | None] = mapped_column(Numeric(24, 4))
    issue_size_shares: Mapped[Decimal | None] = mapped_column(Numeric(24, 4))
    issue_size_crore: Mapped[Decimal | None] = mapped_column(Numeric(24, 4))
    issue_size_crore_is_estimated: Mapped[bool] = mapped_column(Boolean, default=False)
    registrar: Mapped[str | None] = mapped_column(String(300))
    lead_managers: Mapped[list[str] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), index=True
    )
    listings: Mapped[list["ExchangeListing"]] = relationship(back_populates="ipo")
    documents: Mapped[list["IpoDocument"]] = relationship(back_populates="ipo")
    subscriptions: Mapped[list["SubscriptionSnapshot"]] = relationship(back_populates="ipo")
    bid_rules: Mapped[list["BidRule"]] = relationship(back_populates="ipo")
    reservations: Mapped[list["IpoReservation"]] = relationship(back_populates="ipo")


class ExchangeListing(Base):
    __tablename__ = "ipo_exchange_listings"
    __table_args__ = (UniqueConstraint("exchange", "source_id"),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ipo_id: Mapped[int] = mapped_column(ForeignKey("ipos.id", ondelete="RESTRICT"), index=True)
    exchange: Mapped[Exchange] = mapped_column(Enum(Exchange, name="exchange_name"), index=True)
    segment: Mapped[Segment] = mapped_column(Enum(Segment, name="market_segment"), index=True)
    source_id: Mapped[str] = mapped_column(String(100))
    symbol: Mapped[str | None] = mapped_column(String(80))
    series: Mapped[str | None] = mapped_column(String(20))
    scrip_code: Mapped[str | None] = mapped_column(String(20))
    source_status: Mapped[str | None] = mapped_column(String(80))
    source_url: Mapped[str] = mapped_column(Text)
    issue_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    listing_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    listing_close: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    listing_gain_percent: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    missing_runs: Mapped[int] = mapped_column(default=0)
    is_stale: Mapped[bool] = mapped_column(default=False)
    master_data_last_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_refresh_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    detail_failure_count: Mapped[int] = mapped_column(default=0)
    detail_last_error: Mapped[str | None] = mapped_column(Text)
    master_data_finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ipo: Mapped[Ipo] = relationship(back_populates="listings")


class BidRule(Base):
    __tablename__ = "ipo_bid_rules"
    __table_args__ = (UniqueConstraint("ipo_id", "exchange", "category"),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ipo_id: Mapped[int] = mapped_column(ForeignKey("ipos.id", ondelete="CASCADE"), index=True)
    exchange: Mapped[Exchange] = mapped_column(Enum(Exchange, name="bid_rule_exchange"))
    category: Mapped[str] = mapped_column(String(40))
    minimum_bid_quantity: Mapped[int | None] = mapped_column(BigInteger)
    maximum_bid_quantity: Mapped[int | None] = mapped_column(BigInteger)
    maximum_subscription_amount: Mapped[Decimal | None] = mapped_column(Numeric(24, 4))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    ipo: Mapped[Ipo] = relationship(back_populates="bid_rules")


class IpoReservation(Base):
    """Latest durable offer allocation reported by an official source."""

    __tablename__ = "ipo_reservations"
    __table_args__ = (UniqueConstraint("ipo_id", "category"),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ipo_id: Mapped[int] = mapped_column(ForeignKey("ipos.id", ondelete="CASCADE"), index=True)
    category: Mapped[str] = mapped_column(String(40))
    parent_category: Mapped[str | None] = mapped_column(String(40))
    shares: Mapped[Decimal] = mapped_column(Numeric(24, 4))
    source_url: Mapped[str] = mapped_column(Text)
    source_type: Mapped[str] = mapped_column(String(40))
    as_of_date: Mapped[date | None] = mapped_column(Date)
    is_actual: Mapped[bool] = mapped_column(Boolean, default=True)
    is_derived: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    ipo: Mapped[Ipo] = relationship(back_populates="reservations")


class IpoDocument(Base):
    __tablename__ = "ipo_documents"
    __table_args__ = (UniqueConstraint("ipo_id", "document_type", "url"),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ipo_id: Mapped[int] = mapped_column(ForeignKey("ipos.id", ondelete="RESTRICT"), index=True)
    document_type: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(250))
    url: Mapped[str] = mapped_column(Text)
    storage_status: Mapped[str] = mapped_column(String(30), default="NOT_APPLICABLE", index=True)
    storage_key: Mapped[str | None] = mapped_column(Text)
    content_sha256: Mapped[str | None] = mapped_column(String(64), index=True)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    pdf_page_count: Mapped[int | None] = mapped_column()
    pdf_encrypted: Mapped[bool | None] = mapped_column(Boolean)
    pdf_malformed: Mapped[bool | None] = mapped_column(Boolean)
    pdf_inspection_status: Mapped[str] = mapped_column(
        String(30), default="NOT_INSPECTED", index=True
    )
    pdf_processing_decision: Mapped[str | None] = mapped_column(String(50), index=True)
    gemini_direct_eligible: Mapped[bool | None] = mapped_column(Boolean)
    pdf_inspection_error: Mapped[str | None] = mapped_column(Text)
    pdf_inspected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    pdf_processing_status: Mapped[str] = mapped_column(
        String(30), default="NOT_PREPARED", index=True
    )
    pdf_processing_error: Mapped[str | None] = mapped_column(Text)
    pdf_processing_prepared_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_content_type: Mapped[str | None] = mapped_column(String(200))
    final_source_url: Mapped[str | None] = mapped_column(Text)
    storage_attempts: Mapped[int] = mapped_column(default=0)
    storage_error: Mapped[str | None] = mapped_column(Text)
    storage_attempted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    stored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    storage_deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ipo: Mapped[Ipo] = relationship(back_populates="documents")
    processing_files: Mapped[list["RhpProcessingFile"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )
    extraction_jobs: Mapped[list["IpoExtractionJob"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )
    extraction_runs: Mapped[list["IpoExtractionRun"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class RhpProcessingFile(Base):
    """A Gemini-safe PDF and its mapping back to canonical RHP pages."""

    __tablename__ = "rhp_processing_files"
    __table_args__ = (
        UniqueConstraint("document_id", "kind", "chunk_index"),
        Index("ix_rhp_processing_files_document_chunk", "document_id", "chunk_index"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("ipo_documents.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(20))
    chunk_index: Mapped[int | None] = mapped_column()
    storage_key: Mapped[str] = mapped_column(Text)
    content_sha256: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    page_count: Mapped[int] = mapped_column()
    original_start_page: Mapped[int] = mapped_column()
    original_end_page: Mapped[int] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    document: Mapped[IpoDocument] = relationship(back_populates="processing_files")
    extraction_runs: Mapped[list["IpoExtractionRun"]] = relationship(
        back_populates="processing_file"
    )


class IpoExtractionJob(Base):
    """Durable PostgreSQL queue entry for one versioned document extraction."""

    __tablename__ = "ipo_extraction_jobs"
    __table_args__ = (
        UniqueConstraint(
            "document_sha256",
            "model",
            "prompt_version",
            "schema_version",
            name="uq_ipo_extraction_job_identity",
        ),
        Index("ix_ipo_extraction_jobs_claim", "status", "next_attempt_at", "created_at"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("ipo_documents.id", ondelete="CASCADE"), index=True
    )
    document_sha256: Mapped[str] = mapped_column(String(64), index=True)
    model: Mapped[str] = mapped_column(String(100))
    prompt_version: Mapped[str] = mapped_column(String(32))
    schema_version: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), default="QUEUED", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_code: Mapped[str | None] = mapped_column(String(100))
    last_error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    document: Mapped[IpoDocument] = relationship(back_populates="extraction_jobs")
    runs: Mapped[list["IpoExtractionRun"]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )


class IpoExtractionRun(Base):
    """Immutable audit record for a single paid extraction attempt."""

    __tablename__ = "ipo_extraction_runs"
    __table_args__ = (
        Index("ix_ipo_extraction_runs_identity", "document_sha256", "model"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(
        ForeignKey("ipo_extraction_jobs.id", ondelete="CASCADE"), index=True
    )
    document_id: Mapped[int] = mapped_column(
        ForeignKey("ipo_documents.id", ondelete="CASCADE"), index=True
    )
    processing_file_id: Mapped[int | None] = mapped_column(
        ForeignKey("rhp_processing_files.id", ondelete="SET NULL"), index=True
    )
    document_sha256: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(100))
    prompt_version: Mapped[str] = mapped_column(String(32))
    schema_version: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), index=True)
    raw_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    validation_issues: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    request_count: Mapped[int] = mapped_column(Integer, default=1)
    estimated_cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    gemini_file_name: Mapped[str | None] = mapped_column(Text)
    gemini_file_uri: Mapped[str | None] = mapped_column(Text)
    error_code: Mapped[str | None] = mapped_column(String(100))
    error_message: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_by: Mapped[str | None] = mapped_column(String(200))
    review_resolutions: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by: Mapped[str | None] = mapped_column(String(200))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    job: Mapped[IpoExtractionJob] = relationship(back_populates="runs")
    document: Mapped[IpoDocument] = relationship(back_populates="extraction_runs")
    processing_file: Mapped[RhpProcessingFile | None] = relationship(
        back_populates="extraction_runs"
    )
    metrics: Mapped[list["IpoMetric"]] = relationship(
        back_populates="extraction_run", cascade="all, delete-orphan"
    )


class IpoMetric(Base):
    """Canonical reported fact normalized from a versioned RHP extraction."""

    __tablename__ = "ipo_metrics"
    __table_args__ = (
        UniqueConstraint(
            "extraction_run_id",
            "metric",
            "financial_year",
            name="uq_ipo_metric_run_metric_period",
        ),
        Index("ix_ipo_metrics_ipo_metric", "ipo_id", "metric"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ipo_id: Mapped[int] = mapped_column(
        ForeignKey("ipos.id", ondelete="CASCADE"), index=True
    )
    document_id: Mapped[int] = mapped_column(
        ForeignKey("ipo_documents.id", ondelete="CASCADE"), index=True
    )
    extraction_run_id: Mapped[int] = mapped_column(
        ForeignKey("ipo_extraction_runs.id", ondelete="CASCADE"), index=True
    )
    metric: Mapped[str] = mapped_column(String(100), index=True)
    financial_year: Mapped[str | None] = mapped_column(String(20))
    numeric_value: Mapped[Decimal | None] = mapped_column(Numeric(24, 6))
    text_value: Mapped[str | None] = mapped_column(Text)
    unit: Mapped[str | None] = mapped_column(String(32))
    source: Mapped[str] = mapped_column(String(32), default="RHP")
    status: Mapped[str] = mapped_column(String(32))
    provenance: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON)
    verification_status: Mapped[str | None] = mapped_column(String(32))
    extraction_run: Mapped[IpoExtractionRun] = relationship(back_populates="metrics")


class SubscriptionSnapshot(Base):
    __tablename__ = "subscription_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "ipo_id",
            "exchange",
            "captured_at",
            "category",
            "bid_data_scope",
            "content_hash",
            name="uq_subscription_observation",
        ),
        Index("ix_subscription_ipo_time", "ipo_id", "captured_at"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ipo_id: Mapped[int] = mapped_column(ForeignKey("ipos.id", ondelete="RESTRICT"))
    exchange: Mapped[Exchange] = mapped_column(Enum(Exchange, name="subscription_exchange"))
    snapshot_date: Mapped[date] = mapped_column(Date)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    category: Mapped[str] = mapped_column(String(80))
    shares_reserved_for_category: Mapped[Decimal | None] = mapped_column(Numeric(24, 4))
    raw_exchange_bid_quantity: Mapped[Decimal | None] = mapped_column(Numeric(24, 4))
    applications: Mapped[Decimal | None] = mapped_column(Numeric(24, 4))
    calculated_subscription: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    source_reported_multiple: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    source: Mapped[str] = mapped_column(Text)
    bid_data_scope: Mapped[str] = mapped_column(String(30), default="ALL_EXCHANGES")
    content_hash: Mapped[str] = mapped_column(String(64))
    ipo: Mapped[Ipo] = relationship(back_populates="subscriptions")


class SourceRecord(Base):
    __tablename__ = "source_records"
    __table_args__ = (UniqueConstraint("exchange", "source_id"),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    exchange: Mapped[Exchange] = mapped_column(Enum(Exchange, name="source_exchange"))
    source_id: Mapped[str] = mapped_column(String(100))
    endpoint: Mapped[str] = mapped_column(Text)
    payload_hash: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    raw_snapshot_uri: Mapped[str | None] = mapped_column(Text)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    exchange: Mapped[Exchange] = mapped_column(Enum(Exchange, name="run_exchange"), index=True)
    status: Mapped[str] = mapped_column(String(30), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fetched_count: Mapped[int] = mapped_column(default=0)
    inserted_count: Mapped[int] = mapped_column(default=0)
    updated_count: Mapped[int] = mapped_column(default=0)
    rejected_count: Mapped[int] = mapped_column(default=0)
    warnings: Mapped[list[str] | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)
