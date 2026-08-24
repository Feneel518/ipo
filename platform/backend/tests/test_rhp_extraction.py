import json
from types import SimpleNamespace

import pytest

from app.services.rhp.gemini import (
    GeminiStructuredOutputError,
    _api_retry_delay,
    _repair_unresolved_found,
    _truncate_bounded_lists,
    _truncate_bounded_strings,
    create_gemini_client,
    delete_gemini_file,
    extract_rhp_v1,
    upload_pdf_to_gemini,
    wait_for_gemini_file,
)
from app.services.rhp.prompts import RHP_EXTRACTION_PROMPT_V1
from app.services.rhp.schema import RhpExtractionV1
from app.services.rhp.validation import normalize_extraction, validate_extraction


def missing_numeric():
    return {"value": None, "unit": None, "status": "NOT_FOUND", "sources": []}


def found_numeric(value, unit, page=1):
    return {
        "value": value,
        "unit": unit,
        "status": "FOUND",
        "sources": [{"pdf_page": page, "evidence": f"Reported value {value}"}],
    }


def found_text(value, page=1):
    return {
        "value": value,
        "status": "FOUND",
        "sources": [{"pdf_page": page, "evidence": value[:100]}],
    }


def extraction_payload(company_name="Example Limited"):
    return {
        "company": {
            "company_name": company_name,
            "industry": found_text("Industrial manufacturing"),
            "business_description": found_text("Makes engineered products."),
            "products_services": ["Engineered products"],
            "competitive_strengths": [],
            "growth_drivers": [],
        },
        "financials": [
            {
                "financial_year": "FY2026",
                "revenue_from_operations": found_numeric(100, "INR_CRORE", 2),
                "profit_after_tax": found_numeric(10, "INR_CRORE", 2),
                "finance_cost": missing_numeric(),
                "operating_cash_flow": missing_numeric(),
                "trade_receivables": missing_numeric(),
                "total_borrowings": missing_numeric(),
                "total_equity": missing_numeric(),
            }
        ],
        "promoters": {
            "names": ["A Promoter"],
            "pre_issue_holding_pct": found_numeric(75, "PERCENT", 3),
            "post_issue_holding_pct": found_numeric(60, "PERCENT", 3),
            "pledged_shares_pct": missing_numeric(),
        },
        "ipo": {
            "fresh_issue_amount": found_numeric(80, "INR_CRORE", 4),
            "offer_for_sale_amount": found_numeric(20, "INR_CRORE", 4),
            "total_issue_amount": found_numeric(100, "INR_CRORE", 4),
            "price_band_low": found_numeric(100, "INR", 5),
            "price_band_high": found_numeric(110, "INR", 5),
            "lot_size": found_numeric(100, "SHARES", 5),
            "objects_of_issue": [found_text("Fund capital expenditure", 6)],
        },
        "customer_concentration": {
            "top_customer_revenue_pct": missing_numeric(),
            "top_5_customer_revenue_pct": missing_numeric(),
            "top_10_customer_revenue_pct": missing_numeric(),
            "commentary": {
                "value": None,
                "status": "NOT_FOUND",
                "sources": [],
            },
        },
        "peers": [],
        "risks": [
            {
                "title": "Customer concentration",
                "category": "CUSTOMER",
                "description": "Revenue may depend on a limited customer group.",
                "sources": [{"pdf_page": 7, "evidence": "Dependence on key customers"}],
            }
        ],
        "extraction_meta": {"warnings": [], "conflicts": []},
    }


class FakeFiles:
    def __init__(self):
        self.uploads = []
        self.get_counts = {}
        self.deleted = []

    def upload(self, *, file, config):
        name = f"files/rhp-{len(self.uploads) + 1}"
        uploaded = SimpleNamespace(name=name, uri=f"gemini://{name}", state="PROCESSING")
        self.uploads.append((file, config, uploaded))
        return uploaded

    def get(self, *, name):
        self.get_counts[name] = self.get_counts.get(name, 0) + 1
        state = "ACTIVE" if self.get_counts[name] >= 2 else "PROCESSING"
        return SimpleNamespace(name=name, uri=f"gemini://{name}", state=state)

    def delete(self, *, name):
        self.deleted.append(name)


class FakeModels:
    def __init__(self):
        self.calls = []

    def generate_content(self, *, model, contents, config):
        self.calls.append((model, contents, config))
        document_number = (len(self.calls) - 1) // 4 + 1
        payload = extraction_payload(f"Example {document_number} Limited")
        prompt = contents[-1]
        if "company identity" in prompt:
            partial = {"company": payload["company"]}
        elif "restated financial periods" in prompt:
            partial = {"financials": payload["financials"]}
        elif "promoters, IPO terms" in prompt:
            partial = {
                key: payload[key]
                for key in ("promoters", "ipo", "customer_concentration", "peers")
            }
        else:
            partial = {
                "risks": payload["risks"],
                "extraction_meta": payload["extraction_meta"],
            }
        return SimpleNamespace(
            text=json.dumps(partial),
            usage_metadata=SimpleNamespace(
                prompt_token_count=1234,
                candidates_token_count=456,
            ),
        )


class FakeClient:
    def __init__(self):
        self.files = FakeFiles()
        self.models = FakeModels()


def test_compact_v1_schema_rejects_unknown_fields():
    payload = extraction_payload()
    payload["investment_recommendation"] = "BUY"
    with pytest.raises(ValueError):
        RhpExtractionV1.model_validate(payload)


def test_transport_truncates_only_bounded_lists_and_records_warning():
    payload = {"company": {"products_services": [str(index) for index in range(27)]}}
    warnings = []
    _truncate_bounded_lists(payload, warnings=warnings)
    assert len(payload["company"]["products_services"]) == 20
    assert warnings == ["Truncated company.products_services from 27 to 20 items"]


def test_transport_truncates_overlong_evidence_and_records_warning():
    payload = {"sources": [{"evidence": "x" * 450}]}
    warnings = []
    _truncate_bounded_strings(payload, warnings=warnings)
    assert len(payload["sources"][0]["evidence"]) == 400
    assert warnings == [
        "Truncated sources[0].evidence from 450 to 400 characters"
    ]


def test_rate_limit_retry_honors_google_delay():
    error = SimpleNamespace(code=429)
    error.__str__ = lambda: "Please retry in 52.5s"
    assert _api_retry_delay(error, 0) == 60

    class RateLimitError(Exception):
        code = 429

    assert _api_retry_delay(RateLimitError("Please retry in 52.5s"), 0) == 53.5


def test_gemini_client_uses_configured_request_timeout(monkeypatch):
    captured = {}

    def fake_client(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace()

    monkeypatch.setattr("app.services.rhp.gemini.genai.Client", fake_client)
    settings = SimpleNamespace(
        gemini_configured=True,
        gemini_api_key="test-key",
        gemini_request_timeout_seconds=180,
    )
    create_gemini_client(settings)
    assert captured["api_key"] == "test-key"
    assert captured["http_options"].timeout == 180_000


def test_unresolved_found_fact_becomes_not_found():
    payload = {"price_band_low": {"status": "FOUND", "sources": []}}
    warnings = []
    _repair_unresolved_found(payload, warnings=warnings)
    assert payload["price_band_low"]["status"] == "NOT_FOUND"
    assert warnings == [
        "Changed unresolved price_band_low from FOUND to NOT_FOUND"
    ]


def test_explicit_na_found_fact_becomes_not_applicable():
    payload = {
        "offer_for_sale_amount": {
            "value": None,
            "unit": "INR_LAKH",
            "status": "FOUND",
            "sources": [{"evidence": "N.A."}],
        }
    }
    warnings = []
    _repair_unresolved_found(payload, warnings=warnings)
    assert payload["offer_for_sale_amount"]["status"] == "NOT_APPLICABLE"
    assert payload["offer_for_sale_amount"]["unit"] is None


def test_five_single_file_rhps_complete_gemini_happy_path(tmp_path):
    client = FakeClient()
    for index in range(5):
        path = tmp_path / f"ordinary-rhp-{index + 1}.pdf"
        path.write_bytes(b"%PDF-1.7\nfixture\n%%EOF")
        uploaded = upload_pdf_to_gemini(client, path)
        ready = wait_for_gemini_file(
            client,
            uploaded.name,
            timeout_seconds=1,
            poll_seconds=0,
            sleep=lambda _: None,
        )
        generated = extract_rhp_v1(client, ready, model="gemini-3.5-flash-lite")
        delete_gemini_file(client, uploaded.name)

        assert generated.extraction.company.company_name == f"Example {index + 1} Limited"
        assert generated.input_tokens == 4 * 1234
        assert generated.output_tokens == 4 * 456
        assert generated.request_count == 4

    assert len(client.files.uploads) == 5
    assert len(client.models.calls) == 20
    assert len(client.files.deleted) == 5
    assert all(call[0] == "gemini-3.5-flash-lite" for call in client.models.calls)
    assert all(call[2].response_schema is None for call in client.models.calls)
    assert all(call[2].response_json_schema is None for call in client.models.calls)
    assert all("OUTPUT JSON SCHEMA" in call[1][-1] for call in client.models.calls)


def test_invalid_structured_output_preserves_parsed_raw_json():
    client = FakeClient()
    client.models.generate_content = lambda **_: SimpleNamespace(
        text=json.dumps({"company": {}}), usage_metadata=None
    )
    with pytest.raises(GeminiStructuredOutputError) as caught:
        extract_rhp_v1(client, SimpleNamespace(name="files/1"), model="gemini-3.5-flash-lite")
    assert caught.value.raw_json == {"company": {}}


def test_invalid_json_is_retried_at_pass_level():
    client = FakeClient()
    original_generate = client.models.generate_content
    failed_once = False

    def flaky_generate(**kwargs):
        nonlocal failed_once
        if "promoters, IPO terms" in kwargs["contents"][-1] and not failed_once:
            failed_once = True
            client.models.calls.append(
                (kwargs["model"], kwargs["contents"], kwargs["config"])
            )
            return SimpleNamespace(
                text='{"promoters":',
                usage_metadata=SimpleNamespace(
                    prompt_token_count=100,
                    candidates_token_count=10,
                ),
            )
        return original_generate(**kwargs)

    client.models.generate_content = flaky_generate
    generated = extract_rhp_v1(
        client,
        SimpleNamespace(name="files/1"),
        model="gemini-3.5-flash-lite",
    )
    assert generated.request_count == 5
    assert "RETRY CORRECTION" in client.models.calls[3][1][-1]


def test_semantic_validation_checks_page_ranges_and_issue_arithmetic():
    payload = extraction_payload()
    payload["ipo"]["total_issue_amount"]["value"] = 150
    payload["ipo"]["price_band_high"]["sources"][0]["pdf_page"] = 999
    extraction = RhpExtractionV1.model_validate(payload)
    issues = validate_extraction(extraction, page_count=10)
    assert any("exceeds PDF page count" in issue["message"] for issue in issues)
    assert any("Fresh issue + OFS" in issue["message"] for issue in issues)


def test_semantic_validation_rejects_field_specific_units_and_cross_field_ordering():
    payload = extraction_payload()
    payload["ipo"]["lot_size"] = found_numeric(100, "INR", 5)
    payload["ipo"]["price_band_low"] = found_numeric(120, "INR", 5)
    payload["ipo"]["price_band_high"] = found_numeric(110, "INR", 5)
    payload["promoters"]["post_issue_holding_pct"] = found_numeric(80, "PERCENT", 3)
    payload["customer_concentration"]["top_customer_revenue_pct"] = found_numeric(
        40, "PERCENT", 6
    )
    payload["customer_concentration"]["top_5_customer_revenue_pct"] = found_numeric(
        30, "PERCENT", 6
    )
    extraction = RhpExtractionV1.model_validate(payload)
    issues = validate_extraction(extraction, page_count=10)
    codes = {issue["code"] for issue in issues}
    assert "INVALID_UNIT" in codes
    assert "PRICE_BAND_REVERSED" in codes
    assert "PROMOTER_HOLDING_INCREASES_POST_ISSUE" in codes
    assert "CUSTOMER_CONCENTRATION_ORDER" in codes


def test_disputed_values_are_quarantined_but_missing_values_remain_not_found():
    payload = extraction_payload()
    payload["ipo"]["price_band_low"] = found_numeric(120, "INR", 5)
    payload["ipo"]["price_band_high"] = found_numeric(110, "INR", 5)
    payload["ipo"]["lot_size"] = missing_numeric()
    extraction = RhpExtractionV1.model_validate(payload)
    issues = validate_extraction(extraction, page_count=10)
    metrics = normalize_extraction(extraction, issues=issues)
    low = next(item for item in metrics if item.metric == "price_band_low")
    lot = next(item for item in metrics if item.metric == "lot_size")
    assert low.status == "AMBIGUOUS"
    assert low.numeric_value is None
    assert low.unit is None
    assert low.provenance
    assert lot.status == "NOT_FOUND"
    assert lot.numeric_value is None


def test_unsupported_text_is_quarantined_from_canonical_rows():
    payload = extraction_payload()
    payload["company"]["industry"]["sources"] = []
    extraction = RhpExtractionV1.model_validate(payload)
    issues = validate_extraction(extraction, page_count=10)
    industry = next(
        item
        for item in normalize_extraction(extraction, issues=issues)
        if item.metric == "industry"
    )
    assert industry.status == "AMBIGUOUS"
    assert industry.text_value is None


def test_optional_missing_ipo_terms_are_not_critical_but_found_facts_need_sources():
    payload = extraction_payload()
    payload["ipo"]["price_band_low"] = missing_numeric()
    payload["ipo"]["price_band_high"] = missing_numeric()
    payload["customer_concentration"]["top_customer_revenue_pct"] = missing_numeric()
    payload["ipo"]["lot_size"]["sources"] = []
    issues = validate_extraction(RhpExtractionV1.model_validate(payload), page_count=10)
    missing_paths = {
        issue["field_path"]
        for issue in issues
        if issue["code"] == "CRITICAL_FIELD_MISSING"
    }
    assert "ipo.price_band_low" not in missing_paths
    assert "ipo.price_band_high" not in missing_paths
    assert "customer_concentration.top_customer_revenue_pct" not in missing_paths
    assert any(
        issue["code"] == "FOUND_WITHOUT_SOURCE" and issue["field_path"] == "ipo.lot_size"
        for issue in issues
    )


def test_validator_flags_explicit_zero_pledge_left_not_found():
    payload = extraction_payload()
    payload["promoters"]["pledged_shares_pct"] = {
        "value": None,
        "unit": None,
        "status": "NOT_FOUND",
        "sources": [
            {
                "pdf_page": 3,
                "evidence": "None of the Equity Shares held by our Promoters are pledged.",
            }
        ],
    }
    issues = validate_extraction(RhpExtractionV1.model_validate(payload), page_count=10)
    assert any(issue["code"] == "EXPLICIT_ZERO_PLEDGE_MISSED" for issue in issues)


def test_tempsens_pre_issue_value_without_supporting_number_is_suppressed():
    payload = extraction_payload()
    payload["promoters"]["pre_issue_holding_pct"] = {
        "value": 46.13,
        "unit": "PERCENT",
        "status": "FOUND",
        "sources": [{"pdf_page": 1, "evidence": "OUR PROMOTERS: A, B AND C"}],
    }
    extraction = RhpExtractionV1.model_validate(payload)
    issues = validate_extraction(extraction, page_count=10)
    metric = next(
        item for item in normalize_extraction(extraction) if item.metric == "pre_issue_holding_pct"
    )
    assert any(issue["code"] == "VALUE_NOT_IN_EVIDENCE" for issue in issues)
    assert metric.status == "AMBIGUOUS"
    assert metric.numeric_value is None


def test_tempsens_zero_pledge_requires_explicit_no_pledge_evidence():
    payload = extraction_payload()
    payload["promoters"]["pledged_shares_pct"] = {
        "value": 0,
        "unit": "PERCENT",
        "status": "FOUND",
        "sources": [{"pdf_page": 3, "evidence": "- - - - 6,49,47,494"}],
    }
    extraction = RhpExtractionV1.model_validate(payload)
    issues = validate_extraction(extraction, page_count=10)
    metric = next(
        item for item in normalize_extraction(extraction) if item.metric == "pledged_shares_pct"
    )
    assert any(issue["code"] == "VALUE_NOT_IN_EVIDENCE" for issue in issues)
    assert metric.status == "AMBIGUOUS"


def test_explicit_no_pledge_statement_keeps_found_zero_percent():
    payload = extraction_payload()
    payload["promoters"]["pledged_shares_pct"] = {
        "value": 0,
        "unit": "PERCENT",
        "status": "FOUND",
        "sources": [
            {
                "pdf_page": 3,
                "evidence": "None of the Equity Shares held by our Promoters are pledged.",
            }
        ],
    }
    extraction = RhpExtractionV1.model_validate(payload)
    issues = validate_extraction(extraction, page_count=10)
    metric = next(
        item for item in normalize_extraction(extraction) if item.metric == "pledged_shares_pct"
    )
    assert not any(issue["code"] == "VALUE_NOT_IN_EVIDENCE" for issue in issues)
    assert metric.status == "FOUND"
    assert metric.numeric_value == 0
    assert metric.unit == "PERCENT"


def test_sumax_total_borrowings_rejects_separate_debt_components():
    payload = extraction_payload()
    payload["financials"][0]["total_borrowings"] = {
        "value": 642.86,
        "unit": "INR_LAKH",
        "status": "FOUND",
        "sources": [
            {"pdf_page": 4, "evidence": "Long-term Borrowings | 33.20"},
            {"pdf_page": 4, "evidence": "Short Term Borrowings | 609.66"},
        ],
    }
    extraction = RhpExtractionV1.model_validate(payload)
    issues = validate_extraction(extraction, page_count=10)
    metric = next(
        item for item in normalize_extraction(extraction) if item.metric == "total_borrowings"
    )
    assert any(issue["code"] == "BORROWINGS_COMPONENT_ONLY" for issue in issues)
    assert metric.status == "AMBIGUOUS"
    assert metric.numeric_value is None


def test_sumax_total_borrowings_rejects_guaranteed_loan_context():
    payload = extraction_payload()
    payload["financials"][0]["total_borrowings"] = {
        "value": 642.86,
        "unit": "INR_LAKH",
        "status": "FOUND",
        "sources": [
            {
                "pdf_page": 4,
                "evidence": "Aggregate amount of loan guaranteed by directors ... 642.86",
            }
        ],
    }
    extraction = RhpExtractionV1.model_validate(payload)
    issues = validate_extraction(extraction, page_count=10)
    metric = next(
        item for item in normalize_extraction(extraction) if item.metric == "total_borrowings"
    )
    assert any(issue["code"] == "BORROWINGS_COMPONENT_ONLY" for issue in issues)
    assert metric.status == "AMBIGUOUS"


def test_hytech_fiscal_2024_borrowings_rejects_mismatched_citation():
    payload = extraction_payload()
    payload["financials"][0]["total_borrowings"] = found_numeric(
        408.38, "INR_MILLION", 4
    )
    payload["financials"][0]["total_borrowings"]["sources"][0]["evidence"] = (
        "Total debt | 402.34"
    )
    issues = validate_extraction(RhpExtractionV1.model_validate(payload), page_count=10)
    assert any(issue["code"] == "VALUE_NOT_IN_EVIDENCE" for issue in issues)


def test_hytech_fiscal_2025_borrowings_rejects_mismatched_citation():
    payload = extraction_payload()
    payload["financials"][0]["financial_year"] = "Fiscal 2025"
    payload["financials"][0]["total_borrowings"] = found_numeric(
        435.25, "INR_MILLION", 4
    )
    payload["financials"][0]["total_borrowings"]["sources"][0]["evidence"] = (
        "Total debt | 427.97"
    )
    issues = validate_extraction(RhpExtractionV1.model_validate(payload), page_count=10)
    assert any(issue["code"] == "VALUE_NOT_IN_EVIDENCE" for issue in issues)


def test_missing_financial_facts_are_valid_and_remain_skipped():
    payload = extraction_payload()
    for name in (
        "revenue_from_operations",
        "profit_after_tax",
        "finance_cost",
        "operating_cash_flow",
        "trade_receivables",
        "total_borrowings",
        "total_equity",
    ):
        payload["financials"][0][name] = missing_numeric()
    extraction = RhpExtractionV1.model_validate(payload)
    issues = validate_extraction(extraction, page_count=10)
    assert not any(issue["code"] == "CRITICAL_FIELD_MISSING" for issue in issues)
    assert all(
        metric.status == "NOT_FOUND"
        for metric in normalize_extraction(extraction)
        if metric.financial_year == "FY2026"
    )


def test_normalization_creates_reported_metrics_with_provenance():
    extraction = RhpExtractionV1.model_validate(extraction_payload())
    metrics = normalize_extraction(extraction)
    revenue = next(item for item in metrics if item.metric == "revenue_from_operations")
    assert revenue.financial_year == "FY2026"
    assert str(revenue.numeric_value) == "100.0"
    assert revenue.unit == "INR_CRORE"
    assert revenue.provenance[0]["pdf_page"] == 2


def test_prompt_treats_pdf_as_untrusted_and_forbids_recommendations():
    assert "untrusted source material" in RHP_EXTRACTION_PROMPT_V1
    assert "Do not provide investment recommendations" in RHP_EXTRACTION_PROMPT_V1
    assert "at most 300 characters" in RHP_EXTRACTION_PROMPT_V1
    assert "none of the promoter shares are pledged" in RHP_EXTRACTION_PROMPT_V1
    assert "Do not add long-term and short-term debt" in RHP_EXTRACTION_PROMPT_V1
