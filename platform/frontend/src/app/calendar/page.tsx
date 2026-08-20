import type { Metadata } from "next";
import Link from "next/link";
import { EmptyState } from "@/components/empty-state";
import { getCalendar } from "@/lib/api";
import { displayCompanyName, displayDate, humanizeLabel } from "@/lib/format";

export const metadata: Metadata = { title: "IPO Calendar", description: "IPO opening, closing and listing dates across NSE and BSE." };
type Search = Promise<{ month?: string }>;

export default async function CalendarPage({ searchParams }: { searchParams: Search }) {
  const search = await searchParams;
  const now = new Date();
  const fallback = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
  const month = /^\d{4}-\d{2}$/.test(search.month ?? "") ? search.month! : fallback;
  const events = await getCalendar(month);
  const title = new Intl.DateTimeFormat("en-IN", { month: "long", year: "numeric", timeZone: "Asia/Kolkata" }).format(new Date(`${month}-01T00:00:00+05:30`));
  return <section className="calendar-page"><div className="page-title"><p className="overline">Dates that matter</p><h1>IPO calendar</h1><p>Opening, closing and listing events in one chronological rail.</p></div><form className="month-picker"><label htmlFor="month">Choose month</label><input id="month" name="month" type="month" defaultValue={month} /><button className="button button-primary">Show dates</button></form><h2 className="calendar-month">{title}</h2>{events.length ? <ol className="calendar-rail">{events.map((event) => <li key={`${event.ipo_slug}-${event.event_type}`}><time><strong>{new Date(`${event.event_date}T00:00:00+05:30`).getDate()}</strong><span>{displayDate(event.event_date, { weekday: "short" })}</span></time><span className={`event-type event-${event.event_type.toLowerCase()}`}>{humanizeLabel(event.event_type)}</span><div><h3><Link href={`/ipo/${event.ipo_slug}`}>{displayCompanyName(event.company_name)}</Link></h3><p>{humanizeLabel(event.lifecycle)}</p></div><Link href={`/ipo/${event.ipo_slug}`} aria-label={`View ${displayCompanyName(event.company_name)}`}>↗</Link></li>)}</ol> : <EmptyState title="No dates on the rail" variant="calendar" />}</section>;
}
