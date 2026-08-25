import Link from "next/link";
import { AutoRefresh } from "@/components/auto-refresh";
import { getAllIpos, getIpo, getIpos, getSummary } from "@/lib/api";
import { displayCompanyName, displayDate, indiaDateKey, priceBand } from "@/lib/format";
import { firstDayBrief, leadCandidatePool, leadIssueDeck, leadIssueStory, nextInLineBrief, onTheClockBrief, selectLeadIssue, sortUpcoming } from "@/lib/market-briefs";
import type { IpoCardData, IpoDetailData, Subscription } from "@/lib/types";

function market(ipo: IpoCardData) {
  return ipo.listings.map((item) => `${item.exchange}${item.segment === "SME" ? " SME" : ""}`).join(" · ") || "TBA";
}

function overallSubscription(subscriptions: Subscription[]) {
  const latestCaptured = subscriptions.reduce((latest, row) => row.captured_at > latest ? row.captured_at : latest, "");
  const overall = subscriptions.find((row) => row.captured_at === latestCaptured && /^(total|overall)$/i.test(row.category));
  if (overall?.calculated_subscription == null) return null;
  const value = Number(overall?.calculated_subscription);
  return Number.isFinite(value) ? value : null;
}

function IssueRow({ ipo, upcoming = false, overallMultiple = null }: { ipo: IpoCardData; upcoming?: boolean; overallMultiple?: number | null }) {
  return <Link className={upcoming ? "gazette-upcoming-row" : "gazette-open-row"} href={`/ipo/${ipo.slug}`}>
    {!upcoming && <div className="gazette-date"><span>{displayDate(ipo.open_date, { month: "short" })}</span><strong>{ipo.open_date ? new Date(`${ipo.open_date}T00:00:00+05:30`).getDate() : "—"}</strong></div>}
    <div><strong>{displayCompanyName(ipo.company_name)}{!upcoming && overallMultiple != null && <span className="gazette-name-subscription" aria-label={`Overall subscribed ${overallMultiple.toLocaleString("en-IN", { maximumFractionDigits: 2 })} times`}> · {overallMultiple.toLocaleString("en-IN", { maximumFractionDigits: 2 })}×</span>}</strong><small>{market(ipo)}{!upcoming && <> · lot {ipo.lot_size?.toLocaleString("en-IN") ?? "TBA"}{ipo.refund_date && <> · refund {displayDate(ipo.refund_date, { month: "short", day: "numeric" })}{ipo.refund_date_is_estimated ? " · est." : ""}</>}</>}</small></div>
    <div className="gazette-row-terms"><span>{priceBand(ipo.price_low, ipo.price_high)}</span><small>{upcoming ? "Opens" : "Closes"} {displayDate(upcoming ? ipo.open_date : ipo.close_date, { month: "short", day: "numeric" })}</small></div>
  </Link>;
}

export default async function Home() {
  const [summary, openResult, upcomingResult, listed] = await Promise.all([
    getSummary(),
    getAllIpos(new URLSearchParams({ status: "OPEN" })),
    getIpos(new URLSearchParams({ status: "UPCOMING", limit: "50" })),
    getIpos(new URLSearchParams({ status: "LISTED", sort: "listing_date", limit: "2" })),
  ]);
  const open = openResult.data;
  const upcoming = sortUpcoming(upcomingResult.data);
  const leadCandidates = leadCandidatePool(open);
  const openHydrationPool = [...new Map([...leadCandidates, ...open].map((ipo) => [ipo.id, ipo])).values()];
  const hydratedOpen = await Promise.all(openHydrationPool.map(async (ipo) => await getIpo(ipo.slug)));
  const openDetails = new Map(hydratedOpen.flatMap((ipo) => ipo ? [[ipo.id, ipo] as const] : []));
  const hydratedOpenLeadCandidates = leadCandidates.map((ipo) => openDetails.get(ipo.id) ?? ipo);
  const lead = selectLeadIssue(hydratedOpenLeadCandidates, upcoming);
  const hydratedLead = hydratedOpenLeadCandidates.find((ipo) => ipo.id === lead?.id);
  const leadDetail: IpoDetailData | null = hydratedLead && "subscriptions" in hydratedLead
    ? hydratedLead as IpoDetailData
    : lead ? await getIpo(lead.slug) : null;
  const subscriptions = leadDetail?.subscriptions ?? [];
  const latestCaptured = subscriptions.reduce((latest, row) => row.captured_at > latest ? row.captured_at : latest, "");
  const latestSubs = subscriptions.filter((row) => row.captured_at === latestCaptured && row.calculated_subscription != null);
  const overallMultiple = overallSubscription(subscriptions);
  const categorySubs = latestSubs.filter((row) => !/^(total|overall)$/i.test(row.category)).slice(0, 6);
  const maxSub = Math.max(2, ...categorySubs.map((row) => Number(row.calculated_subscription) || 0));
  const leadDeck = leadIssueDeck(overallMultiple != null && Number.isFinite(overallMultiple) ? overallMultiple : null);
  const leadStory = leadDetail ? leadIssueStory(leadDetail, latestSubs) : null;
  const updated = summary.last_updated_at ? new Intl.DateTimeFormat("en-IN", { dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Kolkata" }).format(new Date(summary.last_updated_at)) : "Awaiting first ingestion";

  return <div className="gazette-home">
    <AutoRefresh />
    <section className="gazette-briefs" aria-label="Market summary">
      <article><span>On the clock</span><strong>{summary.open} OPEN</strong><p>{onTheClockBrief(open, indiaDateKey(), summary.open || open.length)}</p></article>
      <article><span>Next in line</span><strong>{summary.upcoming} UPCOMING</strong><p>{nextInLineBrief(upcoming)}</p></article>
      <article><span>First day</span><strong>{summary.listed} LISTED</strong><p>{firstDayBrief(summary, listed.data)}</p></article>
    </section>

    {lead && <section className="lead-issue">
      <div className="lead-copy"><p className="overline">Lead issue · {lead.listings[0]?.segment === "SME" ? "SME" : "Mainboard"}</p><h1>{displayCompanyName(lead.company_name).replace(/ Limited$/i, "")}</h1><p className="lead-deck">{leadDeck}</p><p className="lead-story">{leadStory ?? `Bidding ${lead.open_date ? `opened ${displayDate(lead.open_date, { day: "numeric", month: "long" })}` : "opens on a date to be announced"} at a band of ${priceBand(lead.price_low, lead.price_high)} a share, with a lot of ${lead.lot_size?.toLocaleString("en-IN") ?? "TBA"} shares.`}</p><Link className="gazette-link" href={`/ipo/${lead.slug}`}>Read the full record →</Link></div>
      <div className="lead-subscriptions"><header><span>Subscription by category</span><em>{latestCaptured ? `Exchange timestamp ${new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit", timeZone: "Asia/Kolkata" }).format(new Date(latestCaptured))}` : "Awaiting exchange tape"}</em></header>
        <div className="lead-overall"><span>Overall subscribed</span><strong>{overallMultiple != null && Number.isFinite(overallMultiple) ? overallMultiple.toLocaleString("en-IN", { maximumFractionDigits: 2 }) : "—"}<i>×</i></strong></div>
        {categorySubs.length ? categorySubs.map((row) => { const multiple = Number(row.calculated_subscription) || 0; return <div className="lead-sub-row" key={`${row.exchange}-${row.category}`}><span>{row.category}</span><i><b style={{ width: `${Math.max(3, multiple / maxSub * 100)}%` }} /></i><strong>{multiple.toLocaleString("en-IN", { maximumFractionDigits: 2 })}×</strong></div>; }) : <div className="lead-sub-empty">Category figures have not yet been reported by the exchange.</div>}
        <p>Confirmed bids ÷ reserved shares. Subscription measures demand, not potential listing gain.</p>
      </div>
    </section>}

    <section className="gazette-columns">
      <div><div className="column-heading"><span>Open for subscription</span></div>{open.map((ipo) => <IssueRow ipo={ipo} overallMultiple={overallSubscription(openDetails.get(ipo.id)?.subscriptions ?? [])} key={ipo.id} />)}</div>
      <aside><div className="column-heading"><span>Market note</span></div><blockquote>Dates move. Price bands change. We retain the source trail and show when the data was last refreshed.</blockquote><p className="last-updated">Last refresh {updated}</p><div className="column-heading upcoming-heading"><span>Upcoming issues</span></div>{upcoming.slice(0, 3).map((ipo) => <IssueRow ipo={ipo} upcoming key={ipo.id} />)}{!upcoming.length && listed.data.map((ipo) => <IssueRow ipo={ipo} upcoming key={ipo.id} />)}</aside>
    </section>
  </div>;
}
