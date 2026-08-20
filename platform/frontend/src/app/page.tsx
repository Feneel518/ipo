import Link from "next/link";
import { EmptyState } from "@/components/empty-state";
import { IpoCard } from "@/components/ipo-card";
import { getIpos, getSummary } from "@/lib/api";
import { displayCompanyName, displayDate } from "@/lib/format";

export default async function Home() {
  const [summary, open, upcoming, listed] = await Promise.all([
    getSummary(),
    getIpos(new URLSearchParams({ status: "OPEN", limit: "4" })),
    getIpos(new URLSearchParams({ status: "UPCOMING", limit: "4" })),
    getIpos(new URLSearchParams({ status: "LISTED", sort: "listing_date", limit: "3" })),
  ]);
  const primary = open.data.length ? open.data : upcoming.data;
  const jsonLd = { "@context": "https://schema.org", "@type": "ItemList", itemListElement: primary.map((ipo, index) => ({ "@type": "ListItem", position: index + 1, url: `/ipo/${ipo.slug}`, name: displayCompanyName(ipo.company_name) })) };

  return (
    <>
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd).replace(/</g, "\\u003c") }} />
      <section className="hero">
        <div className="eyebrow"><span>India&apos;s primary market</span><span className="live-dot" /> Daily at 7:30 PM IST</div>
        <div className="hero-grid">
          <div><h1>See the issue.<br /><em>Read the signal.</em></h1><p className="hero-copy">Current, upcoming and recently listed IPOs across NSE, BSE and both SME platforms—sourced from the exchanges, without the noise.</p><div className="hero-actions"><Link className="button button-primary" href="/ipos">Explore all IPOs</Link><Link className="text-link" href="/calendar">Open calendar <span>→</span></Link></div></div>
          <aside className="market-note"><span className="note-index">01 / Market note</span><blockquote>Dates move. Price bands change. We retain the source trail and show when the data was last refreshed.</blockquote><p>Last update<br /><strong>{summary.last_updated_at ? new Intl.DateTimeFormat("en-IN", { dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Kolkata" }).format(new Date(summary.last_updated_at)) : "Awaiting first ingestion"}</strong></p></aside>
        </div>
        <div className="stats-strip" aria-label="IPO summary">
          {[ [summary.open, "Open now"], [summary.upcoming, "Upcoming"], [summary.listed, "Listed"], [summary.sme, "SME issues"] ].map(([value, label]) => <div key={String(label)}><strong>{value}</strong><span>{label}</span></div>)}
        </div>
      </section>

      <section className="section-block">
        <div className="section-heading"><div><span className="section-number">01</span><p className="overline">On the clock</p><h2>{open.data.length ? "Open for subscription" : "Opening next"}</h2></div><Link className="text-link" href="/ipos?status=OPEN">View the board →</Link></div>
        <div className="card-grid">{primary.length ? primary.map((ipo, index) => <IpoCard key={ipo.id} ipo={ipo} priority={index === 0} />) : <EmptyState title="The board is quiet" />}</div>
      </section>

      <section className="section-block paper-panel">
        <div className="section-heading"><div><span className="section-number">02</span><p className="overline">Next in line</p><h2>Upcoming issues</h2></div><Link className="text-link" href="/calendar">Full calendar →</Link></div>
        <div className="editorial-list">{upcoming.data.length ? upcoming.data.map((ipo, index) => <div className="editorial-row" key={ipo.id}><span>{String(index + 1).padStart(2, "0")}</span><div><h3><Link href={`/ipo/${ipo.slug}`}>{displayCompanyName(ipo.company_name)}</Link></h3><p>{ipo.listings.map((item) => `${item.exchange} ${item.segment}`).join(" · ")}</p></div><time>{displayDate(ipo.open_date)}</time><Link href={`/ipo/${ipo.slug}`} aria-label={`View ${displayCompanyName(ipo.company_name)}`}>↗</Link></div>) : <EmptyState />}</div>
      </section>

      <section className="section-block">
        <div className="section-heading"><div><span className="section-number">03</span><p className="overline">First day</p><h2>Recently listed</h2></div></div>
        <div className="card-grid compact">{listed.data.map((ipo) => <IpoCard key={ipo.id} ipo={ipo} />)}{!listed.data.length && <EmptyState />}</div>
      </section>
    </>
  );
}
