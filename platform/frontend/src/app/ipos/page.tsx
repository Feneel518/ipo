import type { Metadata } from "next";
import Link from "next/link";
import { EmptyState } from "@/components/empty-state";
import { IpoCard } from "@/components/ipo-card";
import { getIpos } from "@/lib/api";
import { humanizeLabel } from "@/lib/format";
import { Lifecycle } from "@/lib/types";

export const metadata: Metadata = { title: "All IPOs", description: "Search and filter NSE, BSE, Mainboard and SME IPOs." };

type Search = Promise<Record<string, string | string[] | undefined>>;

export default async function IposPage({ searchParams }: { searchParams: Search }) {
  const incoming = await searchParams;
  const value = (key: string) => typeof incoming[key] === "string" ? incoming[key] as string : "";
  const params = new URLSearchParams();
  for (const key of ["status", "exchange", "segment", "q", "open_from", "open_to", "cursor"]) if (value(key)) params.set(key, value(key));
  params.set("limit", "20");
  const result = await getIpos(params);
  const statuses: Lifecycle[] = ["OPEN", "UPCOMING", "CLOSED", "LISTED"];

  return (
    <section className="listing-page">
      <div className="page-title"><p className="overline">The complete board</p><h1>IPO directory</h1><p>Filter official-source issue data across India&apos;s mainboard and SME exchanges.</p></div>
      <nav className="status-tabs" aria-label="IPO status">
        <Link className={!value("status") ? "active" : ""} href="/ipos">All</Link>
        {statuses.map((status) => <Link className={value("status") === status ? "active" : ""} href={`/ipos?status=${status}`} key={status}>{humanizeLabel(status)}</Link>)}
      </nav>
      <form className="filter-bar" method="get">
        {value("status") && <input type="hidden" name="status" value={value("status")} />}
        <label><span>Search company</span><input name="q" defaultValue={value("q")} placeholder="Company or symbol" /></label>
        <label><span>Exchange</span><select name="exchange" defaultValue={value("exchange")}><option value="">All exchanges</option><option>NSE</option><option>BSE</option></select></label>
        <label><span>Segment</span><select name="segment" defaultValue={value("segment")}><option value="">All segments</option><option value="MAINBOARD">Mainboard</option><option value="SME">SME</option></select></label>
        <button className="button button-primary" type="submit">Apply filters</button>
      </form>
      <p className="result-meta" aria-live="polite">Showing {result.data.length} issues · Updated {result.meta.last_updated_at ? new Date(result.meta.last_updated_at).toLocaleString("en-IN", { timeZone: "Asia/Kolkata" }) : "after the first ingestion"}</p>
      <div className="card-grid directory">{result.data.map((ipo) => <IpoCard ipo={ipo} key={ipo.id} />)}{!result.data.length && <EmptyState />}</div>
      {result.meta.next_cursor && <Link className="button load-more" href={`/ipos?${new URLSearchParams({ ...Object.fromEntries(params), cursor: String(result.meta.next_cursor) })}`}>Next page →</Link>}
    </section>
  );
}
