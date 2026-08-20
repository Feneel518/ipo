export type Lifecycle = "UPCOMING" | "OPEN" | "CLOSED" | "LISTED" | "WITHDRAWN" | "CANCELLED";
export type Exchange = "NSE" | "BSE";
export type Segment = "MAINBOARD" | "SME";
export type MarketType = "BOOK_BUILT" | "FIXED_PRICE" | "UNKNOWN";

export interface Listing {
  exchange: Exchange;
  segment: Segment;
  symbol: string | null;
  series: string | null;
  scrip_code: string | null;
  source_status: string | null;
  issue_price: string | null;
  listing_price: string | null;
  listing_close: string | null;
  listing_gain_percent: string | null;
  source_url: string;
  is_stale: boolean;
  master_data_last_fetched_at: string | null;
}

export interface BidRule {
  exchange: Exchange;
  category: string;
  minimum_bid_quantity: number | null;
  maximum_bid_quantity: number | null;
  maximum_subscription_amount: string | null;
}

export interface IpoCardData {
  id: number;
  company_name: string;
  slug: string;
  lifecycle: Lifecycle;
  open_date: string | null;
  close_date: string | null;
  allotment_date: string | null;
  allotment_date_is_estimated: boolean;
  refund_date: string | null;
  refund_date_is_estimated: boolean;
  credit_date: string | null;
  credit_date_is_estimated: boolean;
  listing_date: string | null;
  price_low: string | null;
  price_high: string | null;
  lot_size: number | null;
  listings: Listing[];
}

export interface Subscription {
  exchange: Exchange;
  snapshot_date: string;
  captured_at: string;
  observed_at: string;
  category: string;
  shares_reserved_for_category?: string | null;
  raw_exchange_bid_quantity?: string | null;
  applications: string | null;
  calculated_subscription?: string | null;
  source_reported_multiple?: string | null;
  source?: string;
  bid_data_scope?: "ALL_EXCHANGES" | "NSE_DISCOVERY" | "BSE_ONLY" | "LEGACY";
}

export interface IpoDetailData extends IpoCardData {
  isin: string | null;
  issue_type: string;
  market_type: MarketType;
  platform: Segment | null;
  exchange_platform: Exchange | "BOTH" | null;
  nse_symbol: string | null;
  nse_series: string | null;
  bse_symbol: string | null;
  bse_scrip_code: string | null;
  final_issue_price: string | null;
  face_value: string | null;
  tick_size: string | null;
  minimum_bid_quantity: number | null;
  minimum_retail_investment: string | null;
  issue_size_shares: string | null;
  issue_size_crore: string | null;
  issue_size_crore_is_estimated: boolean;
  registrar: string | null;
  lead_managers: string[] | null;
  documents: { document_type: string; title: string; url: string }[];
  subscriptions: Subscription[];
  bid_rules: BidRule[];
  master_data_last_fetched_at: string | null;
  master_data_sources: string[];
  last_updated_at: string;
  sources: string[];
}

export interface IpoPageData {
  data: IpoCardData[];
  meta: { next_cursor: number | null; last_updated_at: string | null };
}

export interface Summary {
  open: number;
  upcoming: number;
  listed: number;
  mainboard: number;
  sme: number;
  last_updated_at: string | null;
}

export interface CalendarEvent {
  ipo_slug: string;
  company_name: string;
  event_type: "OPENS" | "CLOSES" | "ALLOTMENT" | "REFUNDS" | "CREDIT" | "LISTS";
  event_date: string;
  lifecycle: Lifecycle;
}
