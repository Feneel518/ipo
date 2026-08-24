"""Small adapter around the pinned Google Gen AI SDK."""

import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from google import genai
from google.genai import types

from app.config import Settings
from app.services.rhp.prompts import RHP_EXTRACTION_PROMPT_V1
from app.services.rhp.schema import (
    CompanyExtractionPass,
    FinancialExtractionPass,
    OfferExtractionPass,
    RhpExtractionV1,
    RiskExtractionPass,
)


class GeminiConfigurationError(RuntimeError):
    pass


class GeminiFileProcessingError(RuntimeError):
    pass


class GeminiStructuredOutputError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        raw_json: dict[str, Any] | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
    ) -> None:
        super().__init__(message)
        self.raw_json = raw_json
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


class GeminiRequestError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        cause: Exception,
        raw_json: dict[str, Any] | None,
        input_tokens: int | None,
        output_tokens: int | None,
        request_count: int,
    ) -> None:
        super().__init__(message)
        self.__cause__ = cause
        self.code = getattr(cause, "code", None)
        self.raw_json = raw_json
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.request_count = request_count


@dataclass(frozen=True)
class GeneratedExtraction:
    extraction: RhpExtractionV1
    raw_json: dict[str, Any]
    input_tokens: int | None
    output_tokens: int | None
    request_count: int


LIST_LIMITS = {
    "sources": 3,
    "products_services": 20,
    "competitive_strengths": 10,
    "growth_drivers": 10,
    "financials": 4,
    "names": 20,
    "objects_of_issue": 10,
    "peers": 15,
    "risks": 15,
    "warnings": 30,
    "conflicts": 30,
}

STRING_LIMITS = {
    "evidence": 400,
}


def _api_retry_delay(exc: Exception, api_attempt: int) -> float:
    if getattr(exc, "code", None) == 429:
        match = re.search(r"retry in ([0-9.]+)s", str(exc), flags=re.IGNORECASE)
        if match:
            return min(float(match.group(1)) + 1, 120)
        return 60
    return (5, 15)[api_attempt]


def _truncate_bounded_lists(value, *, path: str = "", warnings: list[str] | None = None):
    warnings = warnings if warnings is not None else []
    if isinstance(value, dict):
        for key, item in value.items():
            item_path = f"{path}.{key}" if path else key
            limit = LIST_LIMITS.get(key)
            if limit is not None and isinstance(item, list) and len(item) > limit:
                warnings.append(f"Truncated {item_path} from {len(item)} to {limit} items")
                value[key] = item[:limit]
                item = value[key]
            _truncate_bounded_lists(item, path=item_path, warnings=warnings)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _truncate_bounded_lists(item, path=f"{path}[{index}]", warnings=warnings)
    return value


def _truncate_bounded_strings(value, *, path: str = "", warnings: list[str] | None = None):
    """Defensively enforce small model-output string limits before validation."""
    warnings = warnings if warnings is not None else []
    if isinstance(value, dict):
        for key, item in value.items():
            item_path = f"{path}.{key}" if path else key
            limit = STRING_LIMITS.get(key)
            if limit is not None and isinstance(item, str) and len(item) > limit:
                warnings.append(
                    f"Truncated {item_path} from {len(item)} to {limit} characters"
                )
                value[key] = item[:limit].rstrip()
                item = value[key]
            _truncate_bounded_strings(item, path=item_path, warnings=warnings)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _truncate_bounded_strings(item, path=f"{path}[{index}]", warnings=warnings)
    return value


def _repair_unresolved_found(value, *, path: str = "", warnings: list[str] | None = None):
    warnings = warnings if warnings is not None else []
    if isinstance(value, dict):
        if value.get("status") == "FOUND" and value.get("value") is None:
            evidence = [
                source.get("evidence", "")
                for source in value.get("sources", [])
                if isinstance(source, dict)
            ]
            not_applicable = bool(evidence) and all(
                re.fullmatch(r"\s*N\.?\s*A\.?\s*", item, flags=re.IGNORECASE)
                for item in evidence
            )
            replacement = "NOT_APPLICABLE" if not_applicable else "NOT_FOUND"
            value["status"] = replacement
            value["unit"] = None
            warnings.append(
                f"Changed unresolved {path or 'fact'} from FOUND to {replacement}"
            )
        elif (
            value.get("status") == "FOUND"
            and isinstance(value.get("value"), (int, float))
            and value.get("unit") is None
        ):
            value["status"] = "AMBIGUOUS"
            warnings.append(f"Changed unitless {path or 'fact'} from FOUND to AMBIGUOUS")
        elif (
            value.get("status") in {"NOT_FOUND", "NOT_APPLICABLE"}
            and value.get("value") is None
            and "unit" in value
        ):
            value["unit"] = None
        for key, item in value.items():
            item_path = f"{path}.{key}" if path else key
            _repair_unresolved_found(item, path=item_path, warnings=warnings)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _repair_unresolved_found(item, path=f"{path}[{index}]", warnings=warnings)
    return value


def create_gemini_client(settings: Settings):
    if not settings.gemini_configured:
        raise GeminiConfigurationError("GEMINI_API_KEY is not configured")
    return genai.Client(
        api_key=settings.gemini_api_key,
        http_options=types.HttpOptions(
            timeout=settings.gemini_request_timeout_seconds * 1000,
        ),
    )


def _state_name(state: object) -> str:
    name = getattr(state, "name", None)
    if name:
        return str(name).upper()
    value = getattr(state, "value", None)
    if value:
        return str(value).upper().rsplit("_", 1)[-1]
    return str(state or "").upper().rsplit(".", 1)[-1]


def wait_for_gemini_file(
    client,
    file_name: str,
    *,
    timeout_seconds: float = 300,
    poll_seconds: float = 2,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
):
    deadline = monotonic() + timeout_seconds
    while monotonic() < deadline:
        uploaded = client.files.get(name=file_name)
        state = _state_name(uploaded.state)
        if state == "ACTIVE":
            return uploaded
        if state == "FAILED":
            raise GeminiFileProcessingError(
                f"Gemini file processing failed for {file_name}"
            )
        sleep(poll_seconds)
    raise GeminiFileProcessingError(f"Gemini file processing timed out for {file_name}")


def upload_pdf_to_gemini(client, path: Path):
    uploaded = client.files.upload(
        file=str(path),
        config=types.UploadFileConfig(
            mime_type="application/pdf",
            display_name=path.name,
        ),
    )
    if not getattr(uploaded, "name", None):
        raise RuntimeError("Gemini file upload did not return a file name")
    return uploaded


def extract_rhp_v1(
    client,
    uploaded_file,
    *,
    model: str,
    initial_json: dict[str, Any] | None = None,
) -> GeneratedExtraction:
    extraction_passes = (
        (
            "company",
            CompanyExtractionPass,
            "Extract only company identity, industry, business description, products/services, "
            "competitive strengths, and growth drivers.",
        ),
        (
            "financials",
            FinancialExtractionPass,
            "Extract only the available restated financial periods and their requested metrics.",
        ),
        (
            "offer",
            OfferExtractionPass,
            "Extract only promoters, IPO terms and amounts, objects of the issue, customer "
            "concentration, and peers reported in the RHP.",
        ),
        (
            "risks",
            RiskExtractionPass,
            "Extract only the most material risks and extraction warnings or conflicts.",
        ),
    )
    raw_json: dict[str, Any] = dict(initial_json or {})
    total_input_tokens = 0
    total_output_tokens = 0
    input_usage_available = False
    output_usage_available = False
    request_count = 0
    transport_warnings: list[str] = []
    for pass_name, pass_schema, pass_instruction in extraction_passes:
        pass_keys = set(pass_schema.model_fields)
        existing_pass = {key: raw_json[key] for key in pass_keys if key in raw_json}
        if set(existing_pass) == pass_keys:
            _truncate_bounded_lists(existing_pass, warnings=transport_warnings)
            _truncate_bounded_strings(existing_pass, warnings=transport_warnings)
            _repair_unresolved_found(existing_pass, warnings=transport_warnings)
            try:
                pass_schema.model_validate(existing_pass)
                raw_json.update(existing_pass)
                continue
            except Exception:
                pass
        schema_json = json.dumps(pass_schema.model_json_schema(), separators=(",", ":"))
        pass_completed = False
        for structured_attempt in range(2):
            response = None
            retry_note = (
                "\n\nRETRY CORRECTION\nThe prior response was invalid. Return one complete, "
                "strictly valid JSON object matching the schema; do not truncate JSON."
                if structured_attempt
                else ""
            )
            for api_attempt in range(3):
                request_count += 1
                try:
                    response = client.models.generate_content(
                        model=model,
                        contents=[
                            uploaded_file,
                            f"{RHP_EXTRACTION_PROMPT_V1}\n\nPASS SCOPE\n{pass_instruction}"
                            f"\n\nOUTPUT JSON SCHEMA\n{schema_json}{retry_note}",
                        ],
                        config=types.GenerateContentConfig(
                            temperature=0.1,
                            response_mime_type="application/json",
                        ),
                    )
                    break
                except Exception as exc:
                    code = getattr(exc, "code", None)
                    retryable = code == 429 or (isinstance(code, int) and code >= 500)
                    if retryable and api_attempt < 2:
                        time.sleep(_api_retry_delay(exc, api_attempt))
                        continue
                    raise GeminiRequestError(
                        f"Gemini {pass_name} pass request failed: {exc}",
                        cause=exc,
                        raw_json=raw_json or None,
                        input_tokens=total_input_tokens if input_usage_available else None,
                        output_tokens=total_output_tokens if output_usage_available else None,
                        request_count=request_count,
                    ) from exc
            if response is None:
                raise RuntimeError(f"Gemini {pass_name} pass did not produce a response")
            usage = getattr(response, "usage_metadata", None)
            input_tokens = getattr(usage, "prompt_token_count", None)
            output_tokens = getattr(usage, "candidates_token_count", None)
            if input_tokens is not None:
                total_input_tokens += input_tokens
                input_usage_available = True
            if output_tokens is not None:
                total_output_tokens += output_tokens
                output_usage_available = True
            error_metadata = {
                "input_tokens": total_input_tokens if input_usage_available else None,
                "output_tokens": total_output_tokens if output_usage_available else None,
            }
            partial_json = None
            parse_error: Exception | None = None
            if response.text:
                try:
                    candidate = json.loads(response.text)
                    if isinstance(candidate, dict):
                        partial_json = candidate
                except (TypeError, json.JSONDecodeError) as exc:
                    parse_error = exc
            if partial_json is not None:
                _truncate_bounded_lists(partial_json, warnings=transport_warnings)
                _truncate_bounded_strings(partial_json, warnings=transport_warnings)
                _repair_unresolved_found(partial_json, warnings=transport_warnings)
                try:
                    pass_schema.model_validate(partial_json)
                except Exception as exc:
                    parse_error = exc
                else:
                    raw_json.update(partial_json)
                    pass_completed = True
                    break
            if structured_attempt == 1:
                message = (
                    f"Gemini returned invalid JSON for the {pass_name} pass"
                    if parse_error is not None
                    else f"Gemini returned empty or non-object JSON for the {pass_name} pass"
                )
                raise GeminiStructuredOutputError(
                    message,
                    raw_json=(
                        {**raw_json, **partial_json}
                        if partial_json is not None
                        else raw_json or None
                    ),
                    **error_metadata,
                ) from parse_error
        if not pass_completed:
            raise RuntimeError(f"Gemini {pass_name} pass did not complete")
    if transport_warnings:
        meta = raw_json.setdefault("extraction_meta", {"warnings": [], "conflicts": []})
        existing_warnings = meta.setdefault("warnings", [])
        meta["warnings"] = (existing_warnings + transport_warnings)[:30]
    try:
        extraction = RhpExtractionV1.model_validate(raw_json)
    except Exception as exc:
        raise GeminiStructuredOutputError(
            "Merged Gemini JSON did not match RhpExtractionV1",
            raw_json=raw_json,
            input_tokens=total_input_tokens if input_usage_available else None,
            output_tokens=total_output_tokens if output_usage_available else None,
        ) from exc
    return GeneratedExtraction(
        extraction=extraction,
        raw_json=raw_json,
        input_tokens=total_input_tokens if input_usage_available else None,
        output_tokens=total_output_tokens if output_usage_available else None,
        request_count=request_count,
    )


def delete_gemini_file(client, file_name: str) -> None:
    client.files.delete(name=file_name)
