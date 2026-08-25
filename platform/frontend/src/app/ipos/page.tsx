import type { Metadata } from "next";
import Link from "next/link";
import { DirectorySearch } from "@/components/directory-search";
import { getIpos } from "@/lib/api";
import { displayCompanyName, displayDate, humanizeLabel, priceBand } from "@/lib/format";
import { Lifecycle } from "@/lib/types";

export const metadata: Metadata = { title: "IPO Directory", description: "The complete NSE and BSE IPO board." };
type Search = Promise<Record<string, string | string[] | undefined>>;

export default async function IposPage({ searchParams }: { searchParams: Search }) {
  const incoming = await searchParams;
  const status = typeof incoming.status === "string" ? incoming.status : "";
  const query = typeof incoming.q === "string" ? incoming.q.trim() : "";
  const cursor = typeof incoming.cursor === "string" && /^\d+$/.test(incoming.cursor) ? incoming.cursor : "";
  const cursorTrail = typeof incoming.trail === "string"
    ? incoming.trail.split(",").filter((item) => /^\d+$/.test(item)).slice(-50)
    : [];
  const params = new URLSearchParams({ limit: "20" });
  if (status) params.set("status", status);
  if (query) params.set("q", query);
  if (cursor) params.set("cursor", cursor);
  const result = await getIpos(params);
  const statuses: { value: Lifecycle; label: string; description: string }[] = [
    { value: "OPEN", label: "Open", description: "Taking bids" },
    { value: "UPCOMING", label: "Upcoming", description: "Not open yet" },
    { value: "CLOSED", label: "Closed", description: "Bidding ended" },
    { value: "LISTED", label: "Listed", description: "Trading now" },
  ];
  const updated = result.meta.last_updated_at ? new Intl.DateTimeFormat("en-IN", { dateStyle: "long", timeStyle: "short", timeZone: "Asia/Kolkata" }).format(new Date(result.meta.last_updated_at)) : "after the first ingestion";
  const statusHref = (nextStatus = "") => {
    const next = new URLSearchParams();
    if (nextStatus) next.set("status", nextStatus);
    if (query) next.set("q", query);
    const suffix = next.toString();
    return suffix ? `/ipos?${suffix}` : "/ipos";
  };
  const pageHref = (nextCursor = "", nextTrail: string[] = []) => {
    const next = new URLSearchParams();
    if (status) next.set("status", status);
    if (query) next.set("q", query);
    if (nextCursor) next.set("cursor", nextCursor);
    if (nextTrail.length) next.set("trail", nextTrail.join(","));
    const suffix = next.toString();
    return suffix ? `/ipos?${suffix}` : "/ipos";
  };
  const previousCursor = cursorTrail.at(-1) ?? "";
  const previousHref = pageHref(previousCursor, cursorTrail.slice(0, -1));
  const nextHref = result.meta.next_cursor
    ? pageHref(String(result.meta.next_cursor), cursor ? [...cursorTrail, cursor] : cursorTrail)
    : "";
  return <section className="gazette-page gazette-directory">
    <p className="gazette-kicker">The complete board</p><h1>IPO Directory</h1><p className="gazette-intro">Official-source issue data across India&apos;s mainboard and SME exchanges. Showing {result.data.length} issues, updated {updated}.</p>
    <div className="gazette-controls"><nav className="gazette-filters" aria-label="IPO status">
      <Link className={`filter-all${!status ? " active" : ""}`} href={statusHref()} aria-current={!status ? "page" : undefined}><span>All IPOs</span><small>Every status</small></Link>
      {statuses.map((item) => <Link className={`filter-${item.value.toLowerCase()}${status === item.value ? " active" : ""}`} href={statusHref(item.value)} aria-label={`${item.label}: ${item.description}`} aria-current={status === item.value ? "page" : undefined} key={item.value}><span><i aria-hidden="true" />{item.label}</span><small>{item.description}</small></Link>)}
    </nav><DirectorySearch initialQuery={query} status={status} /><span className="directory-result-count" aria-live="polite">{result.data.length} {query ? "matches" : "shown"}</span></div>
    <div className="directory-head"><span>Opens</span><span>Company</span><span>Listing at</span><span>Price band</span><span>Lot</span><span>Closes</span><span>Status</span></div>
    <div className="directory-body">{result.data.map((ipo) => <Link href={`/ipo/${ipo.slug}`} className={`directory-row directory-row-${ipo.lifecycle.toLowerCase()}`} key={ipo.id}>
      <span>{displayDate(ipo.open_date, { month: "short", day: "numeric" })}</span><strong>{displayCompanyName(ipo.company_name)}</strong><span>{ipo.listings.map((item) => `${item.exchange}${item.segment === "SME" ? " SME" : ""}`).join(" · ") || "TBA"}</span><span>{priceBand(ipo.price_low, ipo.price_high)}</span><span>{ipo.lot_size?.toLocaleString("en-IN") ?? "TBA"}</span><span>{displayDate(ipo.close_date, { day: "numeric", month: "short" })}</span><span className={`directory-status directory-status-${ipo.lifecycle.toLowerCase()}`}><i aria-hidden="true" />{humanizeLabel(ipo.lifecycle)}</span>
    </Link>)}{!result.data.length && <p className="directory-empty">No IPOs found{query ? ` for “${query}”` : ""}. Try another company name or status.</p>}</div>
    <p className="gazette-footnote">Rows are drawn from NSE and BSE master data. Select any company to open its record.</p>
    {(cursor || nextHref) && <nav className="gazette-pagination" aria-label="IPO directory pages">
      {cursor && <Link className="gazette-previous" href={previousHref} rel="prev">← Previous page</Link>}
      {nextHref && <Link className="gazette-next" href={nextHref} rel="next">Next page →</Link>}
    </nav>}
  </section>;
}
