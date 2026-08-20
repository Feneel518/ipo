from datetime import UTC, date, datetime
from typing import Any

from app.ingestion.http import get_json, source_client
from app.ingestion.normalize import (
    decimal_value,
    integer_value,
    investor_category,
    lifecycle,
    market_type,
    normalize_name,
    parse_date,
    price_band,
    segment,
)
from app.ingestion.types import BidRuleData, NormalizedIssue, Subscription
from app.models import Exchange, MarketType

BASE = "https://api.bseindia.com/BseIndiaAPI/api"
PAGE = "https://www.bseindia.com/markets/PublicIssues/IPOIssues_new.aspx?id=1&Type=p"
LIVE = f"{BASE}/GetPublicIssue_par_updated/w"
HISTORY = f"{BASE}/HomePage_Issues_BBS_Landing_ng/w"
DETAIL = f"{BASE}/GetMkt_ISSUE_BBS_IPO/w"
PERFORMANCE = f"{BASE}/MoreCompanyN/w"
SECURITY_MASTER = f"{BASE}/ListofScripData/w"


class BSEAdapter:
    exchange = Exchange.BSE

    async def fetch(self, year: int) -> list[NormalizedIssue]:
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Origin": "https://www.bseindia.com",
            "Referer": PAGE,
        }
        rows: dict[str, tuple[dict[str, Any], str]] = {}
        async with source_client() as client:
            live = await get_json(
                client,
                LIVE,
                params={
                    "flag": 1,
                    "scrip_Name": "",
                    "ir_flag": "IPO",
                    "status": "",
                    "exchange": "",
                },
                headers=headers,
            )
            self._add_rows(rows, live, LIVE)
            history = await get_json(
                client,
                HISTORY,
                params={
                    "flag": 2,
                    "scrip_Name": "",
                    "IR_FLAG": "IPO",
                    "Start_DT": f"01/01/{year}",
                    "end_dt": date.today().strftime("%d/%m/%Y"),
                },
                headers=headers,
            )
            self._add_rows(rows, history, HISTORY)
            performance = await get_json(
                client,
                PERFORMANCE,
                params={"Fromdt": year, "company": "", "flag": "", "type": 1},
                headers=headers,
            )
            performance_rows = performance.get("Table", []) if isinstance(performance, dict) else []
            performance_by_name = {
                normalize_name(str(item.get("CompanyName") or "")): item
                for item in performance_rows
                if isinstance(item, dict) and item.get("CompanyName")
            }
            for key, (row, endpoint) in list(rows.items()):
                row_name = normalize_name(str(row.get("Scrip_Name") or row.get("Scrip_name") or ""))
                if row_name in performance_by_name:
                    rows[key] = ({**row, **performance_by_name[row_name]}, endpoint)
            securities = await get_json(
                client,
                SECURITY_MASTER,
                params={
                    "Group": "",
                    "Scripcode": "",
                    "industry": "",
                    "segment": "Equity",
                    "status": "Active",
                },
                headers=headers,
            )
            security_rows = (
                securities.get("Table", []) if isinstance(securities, dict) else securities
            )
            if not isinstance(security_rows, list):
                raise ValueError("BSE contract changed: security master is not a list")
            security_by_name: dict[str, dict[str, Any]] = {}
            for item in security_rows:
                if not isinstance(item, dict):
                    continue
                for field in ("Issuer_Name", "Scrip_Name"):
                    if item.get(field):
                        security_by_name[normalize_name(str(item[field]))] = item
            for key, (row, endpoint) in list(rows.items()):
                row_name = normalize_name(str(row.get("Scrip_Name") or row.get("Scrip_name") or ""))
                if row_name in security_by_name:
                    rows[key] = ({**row, **security_by_name[row_name]}, endpoint)
        return [self._normalize(key, raw, endpoint) for key, (raw, endpoint) in rows.items()]

    async def enrich(
        self, issues: list[NormalizedIssue]
    ) -> tuple[list[NormalizedIssue], dict[str, str]]:
        enriched: list[NormalizedIssue] = []
        errors: dict[str, str] = {}
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Origin": "https://www.bseindia.com",
            "Referer": PAGE,
        }
        async with source_client() as client:
            for issue in issues:
                try:
                    payload = await get_json(
                        client, DETAIL, params={"IPO_NO": issue.source_id}, headers=headers
                    )
                    detail_rows = payload.get("IPONO_0", []) if isinstance(payload, dict) else []
                    if not detail_rows or not isinstance(detail_rows[0], dict):
                        raise ValueError("BSE detail contract changed: IPONO_0 is empty")
                    enriched.append(self._merge_detail(issue, detail_rows[0], payload))
                except Exception as exc:
                    errors[issue.source_id] = str(exc)
                    enriched.append(issue)
        return enriched, errors

    def _merge_detail(
        self, issue: NormalizedIssue, detail: dict[str, Any], payload: dict[str, Any]
    ) -> NormalizedIssue:
        low, high = price_band(detail.get("Price_Band"))
        minimum = integer_value(detail.get("Minimum_Bid_Quantity"))
        rules: list[BidRuleData] = []
        for key, value in detail.items():
            if key.startswith("Maximum_Bid_Quantity") and value not in (None, ""):
                category = investor_category(key.replace("_", " "))
                rules.append(
                    BidRuleData(
                        category=category,
                        minimum_bid_quantity=minimum,
                        maximum_bid_quantity=integer_value(value),
                    )
                )
        if minimum is not None and not rules:
            rules.append(BidRuleData(category="ALL", minimum_bid_quantity=minimum))
        raw_scrip_code = str(detail.get("Scrip_cd") or issue.scrip_code or "")
        scrip_code = (
            raw_scrip_code
            if len(raw_scrip_code) == 6 and raw_scrip_code.isdigit()
            else None
        )
        documents = list(issue.documents)
        document_fields = (
            ("RHP", "Prospectus_GID"),
            ("ADDENDUM", "Addendum"),
            ("CORRIGENDUM", "Corrigendum"),
        )
        for kind, key in document_fields:
            if detail.get(key):
                documents.append((kind, f"{kind} - {issue.company_name}", str(detail[key])))
        detected_market_type = market_type(detail.get("Issue_Type"), low, high)
        updated = issue.model_copy(
            update={
                "company_name": str(detail.get("ScripName") or issue.company_name).strip(),
                "symbol": str(detail.get("Symbol") or issue.symbol or "").upper() or None,
                "scrip_code": scrip_code,
                "price_low": low or issue.price_low,
                "price_high": high or issue.price_high,
                "face_value": decimal_value(detail.get("Face_Value")) or issue.face_value,
                "tick_size": decimal_value(detail.get("Tick_Size")) or issue.tick_size,
                "lot_size": integer_value(detail.get("Market_Lot")) or issue.lot_size,
                "minimum_bid_quantity": minimum or issue.minimum_bid_quantity,
                "issue_size_shares": decimal_value(detail.get("Issue_Size_No_of_shares"))
                or issue.issue_size_shares,
                "market_type": detected_market_type
                if detected_market_type != MarketType.UNKNOWN
                else issue.market_type,
                "registrar": str(detail.get("Registrar") or "").split("^")[0]
                or issue.registrar,
                "documents": documents,
                "bid_rules": rules,
                "detail_raw": payload,
                "detail_endpoint": DETAIL,
                "detail_fetched_at": datetime.now(UTC),
            }
        )
        return updated.with_calculated_values()

    @staticmethod
    def _add_rows(
        target: dict[str, tuple[dict[str, Any], str]], payload: Any, endpoint: str
    ) -> None:
        raw_rows = payload.get("Table", []) if isinstance(payload, dict) else payload
        if not isinstance(raw_rows, list):
            raise ValueError(f"BSE contract changed: {endpoint} has no Table list")
        for row in raw_rows:
            if (
                not isinstance(row, dict)
                or str(row.get("IR_flag") or row.get("IR_FLAG") or "IPO").upper() != "IPO"
            ):
                continue
            key = str(row.get("IPO_NO") or row.get("Scrip_cd") or "")
            if key:
                previous = target.get(key, ({}, endpoint))[0]
                target[key] = ({**previous, **row}, endpoint)

    def _normalize(self, source_id: str, row: dict[str, Any], endpoint: str) -> NormalizedIssue:
        name = str(row.get("Scrip_Name") or row.get("Scrip_name") or source_id).strip()
        opened = parse_date(row.get("Start_Dt") or row.get("ISSUE_START_DT"))
        closed = parse_date(row.get("End_Dt") or row.get("ISSUE_END_DT"))
        listed = parse_date(row.get("Listing_Dt") or row.get("LISTING_DATE") or row.get("ListedOn"))
        low, high = price_band(row.get("Price_Band") or row.get("PRICE_BAND"))
        offered = decimal_value(row.get("OFFERED_QTY") or row.get("Issue_Qty"))
        bids = decimal_value(row.get("BID_QTY") or row.get("CUMM_QTY"))
        multiple = decimal_value(row.get("SUBSCRIPTION") or row.get("NO_OF_TIMES"))
        raw_scrip_code = str(
            row.get("SCRIP_CD") or row.get("SecurityCode") or row.get("Scrip_cd") or ""
        )
        documents = []
        for kind, key in (("RHP", "Prospectus_FILE"), ("ADVERTISEMENT", "ADVERTISE_FILE")):
            if row.get(key):
                documents.append((kind, f"{kind} — {name}", str(row[key])))
        return NormalizedIssue(
            exchange=Exchange.BSE,
            segment=segment(row.get("eXCHANGE_PLATFORM") or row.get("Exchange_Platform")),
            source_id=source_id,
            endpoint=endpoint,
            source_url=str(row.get("NSURL") or PAGE),
            company_name=name,
            normalized_name=normalize_name(name),
            symbol=str(row.get("Symbol") or row.get("scrip_id") or "").upper() or None,
            scrip_code=(
                raw_scrip_code if raw_scrip_code.isdigit() and len(raw_scrip_code) == 6 else None
            ),
            source_status=str(row.get("Status") or "") or None,
            isin=row.get("ISIN") or row.get("ISIN_NUMBER"),
            lifecycle=lifecycle(row.get("Status"), opened, closed, listed),
            open_date=opened,
            close_date=closed,
            listing_date=listed,
            price_low=low,
            price_high=high,
            final_issue_price=decimal_value(row.get("ISSUE_PRICE") or row.get("IssuePrice")),
            face_value=decimal_value(row.get("Face_Val") or row.get("FACE_VALUE")),
            tick_size=decimal_value(row.get("Tick_Size") or row.get("TICK_SIZE")),
            lot_size=integer_value(row.get("Market_Lot") or row.get("MIN_BID_QTY")),
            minimum_bid_quantity=integer_value(
                row.get("Minimum_Bid_Quantity") or row.get("MIN_BID_QTY")
            ),
            issue_size_shares=decimal_value(row.get("Issue_Qty")),
            issue_size_crore=decimal_value(row.get("ISSUE_SIZE_CR")),
            market_type=market_type(row.get("Issue_Type") or row.get("IR_FLAG_FULL"), low, high),
            registrar=row.get("REGISTRAR_NAME"),
            issue_price=decimal_value(row.get("ISSUE_PRICE") or row.get("IssuePrice")),
            listing_price=decimal_value(row.get("LISTING_OPEN")),
            listing_close=decimal_value(row.get("LISTING_CLOSE") or row.get("ListingDayClose")),
            documents=documents,
            subscriptions=[
                Subscription(
                    category="TOTAL",
                    shares_reserved_for_category=offered,
                    raw_exchange_bid_quantity=bids,
                    calculated_subscription=(
                        bids / offered if bids is not None and offered else None
                    ),
                    source_reported_multiple=multiple,
                    source=endpoint,
                    bid_data_scope="BSE_ONLY",
                )
            ]
            if any(item is not None for item in (offered, bids, multiple))
            else [],
            raw=row,
        )
