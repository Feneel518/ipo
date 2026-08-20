import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { AutoRefresh } from "@/components/auto-refresh";
import { StatusPill } from "@/components/status-pill";
import { SubscriptionMomentum } from "@/components/subscription-momentum";
import { getIpo } from "@/lib/api";
import { displayCompanyName, displayDate, humanizeLabel, money, priceBand, quantity } from "@/lib/format";
import { getOverallSubscriptionRating, getSubscriptionRating, ratingScaleLabel } from "@/lib/subscription-rating";

type Params = Promise<{ slug: string }>;

const subscriptionOrder = ["QIB", "NII", "BNII", "SNII", "RETAIL", "EMPLOYEE", "SHAREHOLDER", "TOTAL"];
const subscriptionLabels: Record<string, string> = {
  QIB: "QIB", NII: "NII", BNII: "bNII", SNII: "sNII", RETAIL: "Retail",
  EMPLOYEE: "Employee", SHAREHOLDER: "Shareholder", TOTAL: "Total",
};
const subscriptionDescriptions: Record<string, string> = {
  QIB: "Institutional book", NII: "Non-institutional book", BNII: "Above ₹10 lakh",
  SNII: "₹2–10 lakh", RETAIL: "Individual investors", EMPLOYEE: "Employee quota",
  SHAREHOLDER: "Shareholder quota",
};

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
  const latest = [...new Map(latestRevisions.map((item) => [item.category, item])).values()]
    .sort((left, right) => subscriptionOrder.indexOf(left.category) - subscriptionOrder.indexOf(right.category));
  const latestTimestamp = preferredSnapshot
    ? new Intl.DateTimeFormat("en-IN", { dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Kolkata" }).format(new Date(preferredSnapshot.captured_at))
    : null;
  const snapshotListing = ipo.listings.find((listing) => listing.exchange === preferredSnapshot?.exchange);
  const lastCheckedTimestamp = snapshotListing?.master_data_last_fetched_at
    ? new Intl.DateTimeFormat("en-IN", { dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Kolkata" }).format(new Date(snapshotListing.master_data_last_fetched_at))
    : null;
  const totalSubscription = latest.find((item) => item.category === "TOTAL");
  const categorySubscriptions = latest.filter((item) => item.category !== "TOTAL");
  const segment = ipo.platform ?? ipo.listings[0]?.segment ?? "MAINBOARD";
  const qibSubscription = categorySubscriptions.find((item) => item.category === "QIB");
  const isPreliminary = ipo.lifecycle === "OPEN" && Boolean(ipo.close_date && preferredSnapshot?.snapshot_date < ipo.close_date);
  const overallRating = totalSubscription
    ? getOverallSubscriptionRating({
        rate: Number(totalSubscription.calculated_subscription),
        segment,
        qibRate: qibSubscription ? Number(qibSubscription.calculated_subscription) : undefined,
        preliminary: isPreliminary,
      })
    : null;
  const totalMultipleLabel = totalSubscription
    ? quantity(totalSubscription.calculated_subscription ?? null)
    : "—";
  const totalMultipleSize = totalMultipleLabel.length >= 7
    ? " is-very-long"
    : totalMultipleLabel.length >= 5
      ? " is-long"
      : "";
  const shares = ipo.issue_size_shares ? `${quantity(ipo.issue_size_shares)} shares` : "—";
  const issueSize = ipo.issue_size_crore
    ? `${money(ipo.issue_size_crore)} crore${ipo.issue_size_crore_is_estimated ? " approx." : ""}`
    : "—";
  const marketLot = ipo.lot_size ? `${ipo.lot_size.toLocaleString("en-IN")} shares` : "—";
  const minimumBid = ipo.minimum_bid_quantity
    ? `${ipo.minimum_bid_quantity.toLocaleString("en-IN")} shares`
    : "—";

  const issueFacts = [
    ["Company name", companyName],
    ["Issue type", humanizeLabel(ipo.issue_type)],
    ["Issue status", humanizeLabel(ipo.lifecycle)],
    ["Market type", humanizeLabel(ipo.market_type)],
    ["Platform", ipo.platform ? humanizeLabel(ipo.platform) : "—"],
    ["Exchange platform", ipo.exchange_platform ?? "—"],
    ["NSE symbol", ipo.nse_symbol ?? "—"],
    ["NSE series", ipo.nse_series ?? "—"],
    ["BSE scrip code", ipo.bse_scrip_code ?? "—"],
    ["ISIN", ipo.isin ?? "—"],
    ["Face value", money(ipo.face_value)],
    ["Price band low", money(ipo.price_low)],
    ["Price band high", money(ipo.price_high)],
    ["Final issue price", money(ipo.final_issue_price)],
    ["Tick size", money(ipo.tick_size)],
    ["Lot size", marketLot],
    ["Minimum bid quantity", minimumBid],
    ["Minimum retail investment", money(ipo.minimum_retail_investment)],
    ["Issue size (shares)", shares],
    ["Issue size", issueSize],
  ] as const;

  return (
    <article className="detail-page">
      <AutoRefresh />
      <nav className="breadcrumbs" aria-label="Breadcrumb"><Link href="/">Home</Link><span>/</span><Link href="/ipos">IPOs</Link><span>/</span><span aria-current="page">{companyName}</span></nav>
      <header className="detail-hero">
        <div><div className="card-kicker"><StatusPill status={ipo.lifecycle} /><span>{ipo.listings.map((item) => `${item.exchange} ${item.segment}`).join(" · ")}</span></div><h1>{companyName}</h1><p>{ipo.isin ? `ISIN ${ipo.isin}` : "ISIN pending"} · {humanizeLabel(ipo.issue_type)}</p></div>
        <div className="price-block"><span>Price band</span><strong>{priceBand(ipo.price_low, ipo.price_high)}</strong><small>per equity share</small></div>
      </header>
      <section className="timeline" aria-label="IPO timeline">
        {[ ["Opens", ipo.open_date], ["Closes", ipo.close_date], ["Lists", ipo.listing_date] ].map(([label, date]) => <div key={label}><span>{label}</span><strong>{displayDate(date)}</strong></div>)}
      </section>
      <div className="detail-grid">
        <section><p className="overline">Issue facts</p><h2>Complete issue details</h2><dl className="fact-table fact-table-complete">
          {issueFacts.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}
        </dl></section>
        <aside className="source-panel"><p className="overline">Source trail</p><h2>Exchange records</h2>{ipo.listings.map((listing) => <a href={listing.source_url} target="_blank" rel="noreferrer" key={`${listing.exchange}-${listing.symbol}`}><span>{listing.exchange} · {listing.segment}</span><strong>{listing.symbol ?? listing.scrip_code ?? "Official record"}</strong><small>{listing.is_stale ? "Source record currently stale" : "Verified in latest run"} ↗</small></a>)}<dl className="source-meta"><div><dt>Registrar</dt><dd>{ipo.registrar ?? "To be announced"}</dd></div><div><dt>Last master-data refresh</dt><dd>{ipo.master_data_last_fetched_at ? new Intl.DateTimeFormat("en-IN", { dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Kolkata" }).format(new Date(ipo.master_data_last_fetched_at)) : "Pending"}</dd></div></dl></aside>
      </div>
      <section className="data-section subscription-section" id="demand-book">
        <div className="subscription-heading">
          <div><p className="overline">Demand book</p><h2>Live subscription</h2></div>
          <div className="subscription-freshness"><span className="live-dot" aria-hidden="true" /><div><small>Exchange data as of</small><strong>{latestTimestamp ?? "Waiting for exchange data"}</strong>{lastCheckedTimestamp && <small>Last checked {lastCheckedTimestamp} · page checks every 5 min</small>}</div></div>
        </div>
        {latest.length ? <>
          <div className={`subscription-board${totalSubscription ? "" : " without-total"}`}>
            {totalSubscription && <article className="subscription-total">
              <div className="subscription-total-top"><span>Overall book</span><small>{preferredSnapshot?.exchange} · All exchanges</small></div>
              {overallRating && <span className={`subscription-signal signal-${overallRating.tone}`}>{overallRating.label}</span>}
              <div className={`subscription-total-value${totalMultipleSize}`}><strong>{totalMultipleLabel}</strong><span>×</span></div>
              <p>{overallRating?.summary}</p>
              <div className="subscription-meter subscription-meter-total" aria-label={`${quantity(totalSubscription.calculated_subscription ?? null)} times subscribed`}><span style={{ width: `${Math.min(Number(totalSubscription.calculated_subscription) * 100, 100)}%` }} /></div>
              <div className="subscription-threshold"><span>0×</span><span>1× fully subscribed</span></div>
              <dl><div><dt>Confirmed bids</dt><dd>{quantity(totalSubscription.raw_exchange_bid_quantity ?? null)}</dd></div><div><dt>Reserved shares</dt><dd>{quantity(totalSubscription.shares_reserved_for_category ?? null)}</dd></div>{totalSubscription.applications && <div><dt>Applications</dt><dd>{quantity(totalSubscription.applications)}</dd></div>}</dl>
            </article>}
            <div className="subscription-categories" aria-label="Subscription by investor category">
              {categorySubscriptions.map((item, index) => {
                const multiple = Number(item.calculated_subscription);
                const rating = getSubscriptionRating(multiple, segment);
                return <article className={`subscription-card${multiple >= 1 ? " is-covered" : ""}`} key={`${item.exchange}-${item.category}`}>
                  <header><span>{String(index + 1).padStart(2, "0")}</span><div><small>{subscriptionDescriptions[item.category] ?? "Investor category"}</small><h3>{subscriptionLabels[item.category] ?? humanizeLabel(item.category)}</h3></div><strong>{quantity(item.calculated_subscription ?? null)}<i>×</i></strong></header>
                  <span className={`subscription-signal signal-${rating.tone}`}>{rating.label}</span>
                  <div className="subscription-meter" aria-label={`${quantity(item.calculated_subscription ?? null)} times subscribed`}><span style={{ width: `${Math.min(multiple * 100, 100)}%` }} /></div>
                  <div className="subscription-threshold"><span>Demand</span><span>1× threshold</span></div>
                  <dl><div><dt>Confirmed</dt><dd>{quantity(item.raw_exchange_bid_quantity ?? null)}</dd></div><div><dt>Reserved</dt><dd>{quantity(item.shares_reserved_for_category ?? null)}</dd></div>{item.applications && <div><dt>Applications</dt><dd>{quantity(item.applications)}</dd></div>}</dl>
                </article>;
              })}
            </div>
          </div>
          <footer className="subscription-method"><span>How this is calculated</span><p><strong>Confirmed all-exchange bid quantity</strong><i>÷</i><strong>Shares reserved for category</strong></p><small>{ratingScaleLabel(segment)}. QIB below 1× can make an otherwise good final book “Mixed demand”. Subscription is not a listing-gain forecast.</small>{preferredSnapshot?.source && <a href={preferredSnapshot.source} target="_blank" rel="noreferrer">View official source <b>↗</b></a>}</footer>
          <SubscriptionMomentum subscriptions={auditableSubscriptions} exchange={preferredSnapshot?.exchange} scope={preferredSnapshot?.bid_data_scope} />
        </> : <p className="inline-empty">No auditable subscription snapshot is available yet. Waiting for category reservations and confirmed bid quantities from the exchange.</p>}
      </section>
      {ipo.documents.length > 0 && <section className="data-section"><p className="overline">Filed documents</p><h2>Read the offer material</h2><div className="document-list">{ipo.documents.map((document) => <a href={document.url} target="_blank" rel="noreferrer" key={`${document.document_type}-${document.url}`}><span>{humanizeLabel(document.document_type)}</span>{document.title}<b>↗</b></a>)}</div></section>}
      <div className="risk-note"><strong>Before you apply</strong><p>This page organizes exchange-published information; it is not a recommendation. Read the offer document and assess the risks independently.</p></div>
    </article>
  );
}
