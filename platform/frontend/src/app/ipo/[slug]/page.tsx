import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { AutoRefresh } from "@/components/auto-refresh";
import { ListingBellIllustration } from "@/components/illustrations";
import { IpoTimetable } from "@/components/ipo-timetable";
import { StatusPill } from "@/components/status-pill";
import { SubscriptionMomentum } from "@/components/subscription-momentum";
import { getIpo } from "@/lib/api";
import { displayCompanyName, displayDate, humanizeLabel, indiaDateKey, money, priceBand } from "@/lib/format";
import { ratingScaleLabel } from "@/lib/subscription-rating";

type Params = Promise<{ slug: string }>;

export async function generateMetadata({ params }: { params: Params }): Promise<Metadata> {
  const { slug } = await params;
  const ipo = await getIpo(slug);
  if (!ipo) return { title: "IPO not found" };
  const companyName = displayCompanyName(ipo.company_name);
  return { title: `${companyName} IPO`, description: `${companyName} IPO dates, price band, lot size, subscription and listing information.` };
}

export default async function IpoPage({ params }: { params: Params }) {
  const { slug } = await params;
  const ipo = await getIpo(slug);
  if (!ipo) notFound();
  const companyName = displayCompanyName(ipo.company_name);
  const auditableSubscriptions = ipo.subscriptions.filter((item) =>
    item.shares_reserved_for_category != null && item.raw_exchange_bid_quantity != null && item.calculated_subscription != null
  );
  const preferredSnapshot = auditableSubscriptions.find((item) => item.bid_data_scope === "ALL_EXCHANGES") ?? auditableSubscriptions[0];
  const latestRevisions = auditableSubscriptions
    .filter((item) =>
      item.captured_at === preferredSnapshot?.captured_at
      && item.bid_data_scope === preferredSnapshot?.bid_data_scope
      && item.exchange === preferredSnapshot?.exchange
    )
    .sort((left, right) => Date.parse(right.observed_at) - Date.parse(left.observed_at));
  const latest = [...new Map(latestRevisions.map((item) => [item.category, item])).values()];
  const latestTimestamp = preferredSnapshot
    ? new Intl.DateTimeFormat("en-IN", { dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Kolkata" }).format(new Date(preferredSnapshot.captured_at))
    : null;
  const snapshotListing = ipo.listings.find((listing) => listing.exchange === preferredSnapshot?.exchange);
  const lastCheckedTimestamp = snapshotListing?.master_data_last_fetched_at
    ? new Intl.DateTimeFormat("en-IN", { dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Kolkata" }).format(new Date(snapshotListing.master_data_last_fetched_at))
    : null;
  const segment = ipo.platform ?? ipo.listings[0]?.segment ?? "MAINBOARD";
  const marketLot = ipo.lot_size ? `${ipo.lot_size.toLocaleString("en-IN")} shares` : "—";
  const ipoDates = ipo.open_date && ipo.close_date
    ? `${displayDate(ipo.open_date)} – ${displayDate(ipo.close_date)}`
    : displayDate(ipo.open_date ?? ipo.close_date);
  const listingAt = [...new Set(
    ipo.listings.map((listing) =>
      `${listing.exchange} ${listing.segment === "SME" ? "SME" : "Mainboard"}`,
    ),
  )].join(" · ") || "—";
  const issueType = ipo.market_type === "BOOK_BUILT"
    ? "Book building IPO"
    : ipo.market_type === "FIXED_PRICE"
      ? "Fixed price IPO"
      : humanizeLabel(ipo.issue_type);

  const issueFacts = [
    ["IPO date", ipoDates],
    ["Listing date", displayDate(ipo.listing_date)],
    ["Face value", ipo.face_value ? `${money(ipo.face_value)} per share` : "—"],
    ["Price band", priceBand(ipo.price_low, ipo.price_high)],
    ["Lot size", marketLot],
    ["Sale type", "Not reported by the exchange"],
    ["Issue type", issueType],
    ["Listing at", listingAt],
  ] as const;

  return (
    <article className="detail-page">
      <AutoRefresh />
      <nav className="breadcrumbs" aria-label="Breadcrumb"><Link href="/">Home</Link><span>/</span><Link href="/ipos">IPOs</Link><span>/</span><span aria-current="page">{companyName}</span></nav>
      <header className="detail-hero">
        <div><div className="card-kicker"><StatusPill status={ipo.lifecycle} /><span>{ipo.listings.map((item) => `${item.exchange} ${item.segment}`).join(" · ")}</span></div><h1>{companyName}</h1><p>{ipo.isin ? `ISIN ${ipo.isin}` : "ISIN pending"} · {humanizeLabel(ipo.issue_type)}</p></div>
        <div className="detail-hero-aside">
          <ListingBellIllustration className="detail-hero-illustration" />
          <div className="price-block"><span>Price band</span><strong>{priceBand(ipo.price_low, ipo.price_high)}</strong><small>per equity share</small></div>
        </div>
      </header>
      <IpoTimetable companyName={companyName} openDate={ipo.open_date} closeDate={ipo.close_date} allotmentDate={ipo.allotment_date} allotmentDateIsEstimated={ipo.allotment_date_is_estimated} refundDate={ipo.refund_date} refundDateIsEstimated={ipo.refund_date_is_estimated} creditDate={ipo.credit_date} creditDateIsEstimated={ipo.credit_date_is_estimated} expectedListingDate={ipo.expected_listing_date} listingDate={ipo.listing_date} initialToday={indiaDateKey()} />
      <div className="detail-grid">
        <section className="issue-facts-panel"><div className="issue-facts-heading"><div><p className="overline">Issue facts</p><h2>Key IPO details</h2></div><span aria-hidden="true">08 / essentials</span></div><dl className="fact-table fact-table-complete" aria-label={`${companyName} key IPO details`}>
          {issueFacts.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}
        </dl></section>
        <aside className="source-panel" aria-labelledby="source-panel-title">
          <header className="source-panel-heading">
            <div><p className="overline">Source trail</p><h2 id="source-panel-title">Exchange records</h2></div>
          </header>
          <div className="source-record-list">
            {ipo.listings.map((listing, index) => <a href={listing.source_url} target="_blank" rel="noreferrer" key={`${listing.exchange}-${listing.symbol}`}>
              <span className="source-record-top"><b>{String(index + 1).padStart(2, "0")} · {listing.exchange} {listing.segment}</b><i className={listing.is_stale ? "is-stale" : ""}>{listing.is_stale ? "Stale" : "Verified"}</i></span>
              <strong>{listing.symbol ?? listing.scrip_code ?? "Official record"}</strong>
              <small>Open exchange record <b aria-hidden="true">↗</b></small>
            </a>)}
          </div>
          <dl className="source-meta"><div><dt>Registrar</dt><dd>{ipo.registrar ?? "To be announced"}</dd></div><div><dt>Last master-data refresh</dt><dd>{ipo.master_data_last_fetched_at ? new Intl.DateTimeFormat("en-IN", { dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Kolkata" }).format(new Date(ipo.master_data_last_fetched_at)) : "Pending"}</dd></div></dl>
        </aside>
      </div>
      {ipo.lifecycle === "OPEN" && <section className="live-book" id="demand-book">
        <header className="live-book-heading">
          <div><p className="overline">Live issue demand</p><h2>The book,<br /><em>in motion.</em></h2><p>Follow subscription as confirmed exchange bids enter the book.</p></div>
          <div className="live-book-stamp"><span className="live-dot" aria-hidden="true" /><div><small>Exchange timestamp</small><strong>{latestTimestamp ?? "Awaiting first update"}</strong>{lastCheckedTimestamp && <small>Checked {lastCheckedTimestamp} · refreshes every 5 min</small>}</div></div>
        </header>
        {latest.length ? <>
          <SubscriptionMomentum subscriptions={auditableSubscriptions} exchange={preferredSnapshot?.exchange} scope={preferredSnapshot?.bid_data_scope} />
          <footer className="live-book-method"><div><span>Method</span><strong>Confirmed bids ÷ reserved shares</strong></div><p>{ratingScaleLabel(segment)}. Subscription measures demand, not potential listing gain.</p>{preferredSnapshot?.source && <a href={preferredSnapshot.source} target="_blank" rel="noreferrer">Official exchange source <b>↗</b></a>}</footer>
        </> : <p className="live-book-empty">The exchange has not published an auditable subscription snapshot yet.</p>}
      </section>}
      {ipo.documents.length > 0 && <section className="data-section"><p className="overline">Filed documents</p><h2>Read the offer material</h2><div className="document-list">{ipo.documents.map((document) => <a href={document.url} target="_blank" rel="noreferrer" key={`${document.document_type}-${document.url}`}><span>{humanizeLabel(document.document_type)}</span>{document.title}<b>↗</b></a>)}</div></section>}
      <div className="risk-note"><strong>Before you apply</strong><p>This page organizes exchange-published information; it is not a recommendation. Read the offer document and assess the risks independently.</p></div>
    </article>
  );
}
