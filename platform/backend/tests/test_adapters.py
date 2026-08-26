from decimal import Decimal

from app.ingestion.bse import BSEAdapter
from app.ingestion.normalize import price_band
from app.ingestion.nse import NSEAdapter, normalize_all_exchange_subscriptions
from app.models import Lifecycle, Segment


def test_nse_contract_normalization():
    issue = NSEAdapter()._normalize(
        "TEST",
        {
            "companyName": "Test Limited",
            "symbol": "TEST",
            "series": "SME",
            "issueStartDate": "20-Aug-2026",
            "issueEndDate": "22-Aug-2026",
            "basisOfAllotmentDate": "24-Aug-2026",
            "refundDate": "25-Aug-2026",
            "creditOfSharesDate": "25-Aug-2026",
            "listingDate": "26-Aug-2026",
            "issuePrice": "Rs. 100 to Rs. 110",
            "noOfTime": "2.35",
        },
        "fixture",
    )
    assert issue.segment == Segment.SME
    assert issue.lifecycle in {
        Lifecycle.UPCOMING,
        Lifecycle.OPEN,
        Lifecycle.CLOSED,
        Lifecycle.LISTED,
    }
    assert issue.subscriptions[0].source_reported_multiple == Decimal("2.35")
    assert issue.allotment_date.isoformat() == "2026-08-24"
    assert issue.refund_date.isoformat() == "2026-08-25"
    assert issue.credit_date.isoformat() == "2026-08-25"
    assert issue.allotment_date_is_estimated is False


def test_nse_all_exchange_categories_keep_raw_values_and_calculate_subscription():
    subscriptions = normalize_all_exchange_subscriptions(
        {
            "updateTime": "Updated as on 19-Aug-2026 15:15:00 hrs",
            "dataList": [
                {
                    "category": "Category",
                    "noOfShareOffered": "No.of shares offered/reserved",
                },
                {
                    "category": "Qualified Institutional Buyers(QIBs)",
                    "noOfShareOffered": "1,000,000",
                    "noOfSharesBid": "4,810,000",
                    "noOfTotalMeant": "4.81",
                    "noOfApplications": "120",
                },
                {
                    "category": "Non Institutional Investors",
                    "noOfShareOffered": "500000",
                    "noOfSharesBid": "6210000",
                    "noOfTotalMeant": "12.42",
                },
                {
                    "category": (
                        "Non Institutional Investors(Bid amount of more than Ten Lakh Rupees)"
                    ),
                    "noOfShareOffered": "250000",
                    "noOfSharesBid": "2075000",
                },
                {
                    "category": (
                        "Non Institutional Investors(Bid amount of more than Two Lakh Rupees "
                        "upto Ten Lakh Rupees)"
                    ),
                    "noOfShareOffered": "250000",
                    "noOfSharesBid": "4647500",
                },
                {
                    "category": "Retail Individual Investors(RIIs)",
                    "noOfShareOffered": "2500000",
                    "noOfSharesBid": "16825000",
                    "noOfTotalMeant": "6.72",
                },
                {
                    "category": "Cut Off",
                    "noOfShareOffered": "",
                    "noOfSharesBid": "10000000",
                },
            ],
        }
    )

    by_category = {item.category: item for item in subscriptions}
    assert set(by_category) == {"QIB", "NII", "BNII", "SNII", "RETAIL"}
    assert by_category["QIB"].applications == Decimal("120")
    assert by_category["RETAIL"].shares_reserved_for_category == Decimal("2500000")
    assert by_category["RETAIL"].raw_exchange_bid_quantity == Decimal("16825000")
    assert by_category["RETAIL"].calculated_subscription == Decimal("6.73")
    assert by_category["RETAIL"].source_reported_multiple == Decimal("6.72")
    assert by_category["RETAIL"].captured_at.isoformat() == "2026-08-19T15:15:00+05:30"
    assert by_category["RETAIL"].bid_data_scope == "ALL_EXCHANGES"


def test_bse_contract_normalization():
    issue = BSEAdapter()._normalize(
        "42",
        {
            "Scrip_Name": "Example Limited",
            "Scrip_cd": 500042,
            "eXCHANGE_PLATFORM": "MainBoard",
            "Start_Dt": "2026-08-17T00:00:00",
            "End_Dt": "2026-08-19T00:00:00",
            "Price_Band": "57.00 - 60.00",
            "ListedOn": "2026-08-25T00:00:00",
            "Basis_Of_Allotment_Date": "2026-08-21T00:00:00",
            "Refund_Date": "2026-08-24T00:00:00",
            "Credit_Of_Shares_Date": "2026-08-24T00:00:00",
            "IssuePrice": 60,
            "ListingDayClose": 72,
        },
        "fixture",
    )
    assert issue.segment == Segment.MAINBOARD
    assert issue.price_high == 60
    assert issue.listing_date.isoformat() == "2026-08-25"
    assert issue.issue_price == 60
    assert issue.listing_close == 72
    assert issue.allotment_date.isoformat() == "2026-08-21"
    assert issue.refund_date.isoformat() == "2026-08-24"
    assert issue.credit_date.isoformat() == "2026-08-24"


def test_price_band_ignores_amounts_in_appended_bse_notes():
    low, high = price_band(
        "92.00-97.00|/Employee Discount of Rs 9 to Eligible Employees|"
    )

    assert low == Decimal("92.00")
    assert high == Decimal("97.00")


def test_bse_security_master_identifiers_are_not_confused_with_ipo_number():
    issue = BSEAdapter()._normalize(
        "4734",
        {
            "Scrip_Name": "Example Limited",
            "Scrip_cd": 4734,
            "SCRIP_CD": "544870",
            "scrip_id": "EXAMPLE",
            "ISIN_NUMBER": "INE1EEM01017",
            "eXCHANGE_PLATFORM": "MainBoard",
        },
        "fixture",
    )
    assert issue.source_id == "4734"
    assert issue.scrip_code == "544870"
    assert issue.symbol == "EXAMPLE"
    assert issue.isin == "INE1EEM01017"
