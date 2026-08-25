import type { Metadata } from "next";
import { AllotmentChanceMarquee } from "@/components/allotment-chance-marquee";
import { DeferredSubscriptionMomentum } from "@/components/deferred-subscription-momentum";
import { getIpo, getIpos } from "@/lib/api";
import { displayCompanyName, quantity } from "@/lib/format";

export const metadata: Metadata = {
  title: "IPO subscriptions",
  description: "Latest confirmed IPO subscription figures by investor category.",
};

type SearchParams = Promise<{ ipo?: string | string[] }>;

export default async function SubscriptionsPage({ searchParams }: { searchParams: SearchParams }) {
  const requestedIpo = (await searchParams).ipo;
  const requestedSlug = Array.isArray(requestedIpo) ? requestedIpo[0] : requestedIpo;
  const open = requestedSlug
    ? null
    : await getIpos(new URLSearchParams({ status: "OPEN", sort: "open_date", limit: "1" }));
  const slug = requestedSlug ?? open?.data[0]?.slug;
  const ipo = slug ? await getIpo(slug) : null;
  const rows = (ipo?.subscriptions ?? []).filter((row) => row.calculated_subscription != null);
  const capturedAt = rows.reduce((latest, row) => row.captured_at > latest ? row.captured_at : latest, "");
  const latestSnapshotRows = rows.filter((row) => row.captured_at === capturedAt);
  const preferredRow = latestSnapshotRows.find((row) => row.bid_data_scope === "ALL_EXCHANGES") ?? latestSnapshotRows[0];
  const latestRevisions = latestSnapshotRows
    .filter((row) => row.exchange === preferredRow?.exchange && row.bid_data_scope === preferredRow?.bid_data_scope)
    .sort((left, right) => Date.parse(right.observed_at) - Date.parse(left.observed_at));
  const latest = [...new Map(latestRevisions.map((row) => [row.category, row])).values()];
  const max = Math.max(1, ...latest.map((row) => Number(row.calculated_subscription) || 0));
  const overall = latest.find((row) => /^(total|overall)$/i.test(row.category)) ?? latest[0];

  return (
    <section className="gazette-page gazette-book">
      <p className="gazette-kicker">Live issue demand</p>
      <h1>The Book, in Motion</h1>
      <header>
        <p>Subscription for <strong>{ipo ? displayCompanyName(ipo.company_name) : "the lead issue"}</strong> as confirmed exchange bids enter the book, refreshed every five minutes while the issue is open.</p>
        <div><span>Overall book</span><strong>{overall?.calculated_subscription ? Number(overall.calculated_subscription).toLocaleString("en-IN", { maximumFractionDigits: 2 }) : "—"}×</strong><small>Confirmed exchange demand</small></div>
      </header>
      {ipo && <AllotmentChanceMarquee ipo={ipo} latestSubscriptions={latest} />}
      <div className="book-head"><span>Category</span><span>Cover</span><span>Confirmed bids</span><span>Reserved shares</span><span>Change</span></div>
      {latest.map((row) => {
        const value = Number(row.calculated_subscription) || 0;
        return <div className="book-row" key={`${row.exchange}-${row.bid_data_scope}-${row.category}`}><span>{row.category}</span><span><i><b style={{ width: `${Math.max(3, value / max * 100)}%` }} /></i><strong>{value.toLocaleString("en-IN", { maximumFractionDigits: 2 })}×</strong></span><span>{quantity(row.raw_exchange_bid_quantity ?? null)}</span><span>{quantity(row.shares_reserved_for_category ?? null)}</span><span>Latest</span></div>;
      })}
      {!latest.length && <p className="lead-sub-empty">The exchange has not published subscription figures for this issue yet.</p>}
      {ipo && preferredRow && <DeferredSubscriptionMomentum slug={ipo.slug} exchange={preferredRow.exchange} scope={preferredRow.bid_data_scope} />}
      <div className="book-method"><p>Method: confirmed bids divided by reserved shares. Subscription measures demand, not potential listing gain.</p><p>Final allotment odds depend on valid applications and the published basis of allotment.</p></div>
    </section>
  );
}
