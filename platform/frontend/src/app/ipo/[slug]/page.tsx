import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { AutoRefresh } from "@/components/auto-refresh";
import { AllotmentChanceMarquee } from "@/components/allotment-chance-marquee";
import { IpoTimetable } from "@/components/ipo-timetable";
import { ApplicationSizes, ReservedPools } from "@/components/offer-structure";
import { RememberIpoRecord } from "@/components/remember-ipo-record";
import { CompanyOverview, RhpAnalysis } from "@/components/rhp-analysis";
import { getIpo } from "@/lib/api";
import { displayCompanyName, displayDate, humanizeLabel, money, priceBand } from "@/lib/format";

type Params = Promise<{ slug: string }>;

// Create IPO records on demand, then keep the rendered result in ISR. This
// avoids prebuilding hundreds of records while making repeat visits CDN-fast.
export const revalidate = 300;
export async function generateStaticParams() {
  return [];
}

export async function generateMetadata({ params }: { params: Params }): Promise<Metadata> {
  const { slug } = await params;
  const ipo = await getIpo(slug);
  if (!ipo) return { title: "IPO not found" };
  const companyName = displayCompanyName(ipo.company_name);
  return { title: `${companyName} IPO`, description: `${companyName} IPO dates, price band, lot size, subscription and listing information.` };
}

const stamp = (value: string | null | undefined) => value
  ? new Intl.DateTimeFormat("en-IN", { dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Kolkata" }).format(new Date(value))
  : null;

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
  const overall = latest.find((row) => row.category === "TOTAL")
    ?? latest.reduce<typeof latest[number] | undefined>((best, row) =>
      !best || Number(row.calculated_subscription) > Number(best.calculated_subscription) ? row : best, undefined);
  const overallLabel = overall?.calculated_subscription
    ? Number(overall.calculated_subscription).toLocaleString("en-IN", { maximumFractionDigits: 2 })
    : null;

  const snapshotListing = ipo.listings.find((listing) => listing.exchange === preferredSnapshot?.exchange);
  const tape = [
    stamp(preferredSnapshot?.captured_at) ? `Exchange timestamp ${stamp(preferredSnapshot?.captured_at)}` : "No exchange tape for this issue yet",
    stamp(snapshotListing?.master_data_last_fetched_at) ? `checked ${stamp(snapshotListing?.master_data_last_fetched_at)}` : null,
  ].filter(Boolean).join(" · ");

  const marketLot = ipo.lot_size ? `${ipo.lot_size.toLocaleString("en-IN")} shares` : "—";
  const ipoDates = ipo.open_date && ipo.close_date
    ? `${displayDate(ipo.open_date)} – ${displayDate(ipo.close_date)}`
    : displayDate(ipo.open_date ?? ipo.close_date);
  const listingAt = [...new Set(ipo.listings.map((listing) => `${listing.exchange} ${listing.segment === "SME" ? "SME" : "Mainboard"}`))].join(" · ") || "—";
  const issueType = ipo.market_type === "BOOK_BUILT"
    ? "Book building IPO"
    : ipo.market_type === "FIXED_PRICE"
      ? "Fixed price IPO"
      : humanizeLabel(ipo.issue_type);
  const rhpSourceUrl = ipo.documents.find((document) => document.document_type.toUpperCase().includes("RHP"))?.url;

  const issueFacts = [
    ["IPO date", ipoDates],
    ["Listing date", displayDate(ipo.listing_date)],
    ["Face value", ipo.face_value ? `${money(ipo.face_value)} per share` : "—"],
    ["Lot size", marketLot],
    ["Issue type", issueType],
    ["Listing at", listingAt],
    ["ISIN", ipo.isin ?? "Pending"],
    ["Registrar", ipo.registrar ?? "To be announced"],
    ["Master-data refresh", stamp(ipo.master_data_last_fetched_at) ?? "Pending"],
  ] as const;

  return (
    <article className="record">
      <AutoRefresh />
      <RememberIpoRecord slug={slug} />
      <nav className="breadcrumbs" aria-label="Breadcrumb">
        <Link href="/ipos">Directory</Link><span>/</span><span aria-current="page">{companyName}</span>
      </nav>

      <header className="record-head">
        <div>
          <h1>{companyName}</h1>
          <p className="record-meta">{humanizeLabel(ipo.lifecycle)} · {listingAt} · {issueType}</p>
        </div>
        <div className="record-band">
          <span>Price band</span>
          <strong>{priceBand(ipo.price_low, ipo.price_high)}</strong>
          <small>per equity share · lot of {ipo.lot_size?.toLocaleString("en-IN") ?? "TBA"}</small>
        </div>
      </header>

      <AllotmentChanceMarquee ipo={ipo} latestSubscriptions={latest} />

      {ipo.rhp_analysis && <CompanyOverview analysis={ipo.rhp_analysis} approvedAt={ipo.rhp_approved_at} status={ipo.rhp_analysis_status} sourceUrl={rhpSourceUrl} />}

      <div className="record-columns">
        <div className={ipo.lot_size_applications?.length ? "record-tables record-tables-balanced" : "record-tables"}>
          <IpoTimetable
            companyName={companyName}
            openDate={ipo.open_date}
            closeDate={ipo.close_date}
            allotmentDate={ipo.allotment_date}
            allotmentDateIsEstimated={ipo.allotment_date_is_estimated}
            refundDate={ipo.refund_date}
            refundDateIsEstimated={ipo.refund_date_is_estimated}
            creditDate={ipo.credit_date}
            creditDateIsEstimated={ipo.credit_date_is_estimated}
            expectedListingDate={ipo.expected_listing_date}
            listingDate={ipo.listing_date}
          />
          <ApplicationSizes ipo={ipo} />
        </div>
        <aside>
          <div className="column-heading"><span>Key details</span></div>
          <dl>
            {issueFacts.map(([label, value]) => <div className="fact-row" key={label}><dt>{label}</dt><dd>{value}</dd></div>)}
          </dl>

          {ipo.documents.length > 0 && <div className="record-section">
            <div className="column-heading"><span>Filed documents</span></div>
            {ipo.documents.map((document) => <a className="doc-row" href={document.url} target="_blank" rel="noreferrer" key={`${document.document_type}-${document.url}`}>
              <span className="doc-kind">{humanizeLabel(document.document_type)}</span>
              {document.title} <b aria-hidden="true">↗</b>
            </a>)}
          </div>}

          <div className="record-section">
            <div className="column-heading"><span>Source trail</span></div>
            {ipo.listings.map((listing) => <a className="doc-row" href={listing.source_url} target="_blank" rel="noreferrer" key={`${listing.exchange}-${listing.symbol}`}>
              <span className="doc-kind">{listing.exchange} {listing.segment} · {listing.is_stale ? "Stale" : "Verified"}</span>
              {listing.symbol ?? listing.scrip_code ?? "Official record"} <b aria-hidden="true">↗</b>
            </a>)}
          </div>

          <p className="record-notice">This page organizes exchange-published information. It is not a recommendation. Read the offer document and assess the risks independently.</p>
        </aside>
      </div>

      <ReservedPools ipo={ipo} latestSubscriptions={latest} />

      {ipo.rhp_analysis && <RhpAnalysis analysis={ipo.rhp_analysis} />}

      <div className="demand-strip">
        <div>
          <p className="overline">Live issue demand</p>
          <h2>The book, <em>in motion</em></h2>
          <p>{tape}</p>
        </div>
        <div>
          <strong>{overallLabel ? `${overallLabel}×` : "—"}</strong>
          <Link href={`/subscriptions?ipo=${encodeURIComponent(ipo.slug)}`}>Full subscription tape →</Link>
        </div>
      </div>
    </article>
  );
}
