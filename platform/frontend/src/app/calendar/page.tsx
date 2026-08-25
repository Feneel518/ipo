import type { Metadata } from "next";
import Link from "next/link";
import { CalendarNavigator } from "@/components/calendar-navigator";
import { getCalendar } from "@/lib/api";
import { displayCompanyName, humanizeLabel, indiaDateKey } from "@/lib/format";

export const metadata: Metadata = { title: "Calendar", description: "IPO opening, closing, allotment and listing dates." };
type Search = Promise<{ date?: string; month?: string }>;

export default async function CalendarPage({ searchParams }: { searchParams: Search }) {
  const search = await searchParams;
  const today = indiaDateKey();
  const fallback = today.slice(0, 7);
  const month = /^\d{4}-\d{2}$/.test(search.month ?? "") ? search.month! : fallback;
  const requestedDate = /^\d{4}-\d{2}-\d{2}$/.test(search.date ?? "") ? search.date! : "";
  const events = await getCalendar(month);
  const days = [...new Map(events.map((event) => [event.event_date, events.filter((item) => item.event_date === event.event_date)])).entries()];

  return <section className="gazette-page gazette-calendar">
    <p className="gazette-kicker">Diary of the primary market</p><h1>Calendar</h1>
    <CalendarNavigator availableDates={days.map(([date]) => date)} displayedMonth={month} initialDate={requestedDate} today={today} />
    {days.map(([date, dayEvents]) => {
      const value = new Date(`${date}T00:00:00+05:30`);
      return <section className="gazette-calendar-day" id={`date-${date}`} key={date}>
        <time dateTime={date}><strong>{value.getDate()}</strong><span>{new Intl.DateTimeFormat("en-IN", { month: "short" }).format(value)} · {new Intl.DateTimeFormat("en-IN", { weekday: "long" }).format(value)}</span></time>
        <div>{dayEvents.map((event) => <Link href={`/ipo/${event.ipo_slug}`} className="gazette-calendar-event" key={`${event.ipo_slug}-${event.event_type}`}><span>{humanizeLabel(event.event_type)}</span><strong>{displayCompanyName(event.company_name)}</strong><span>{humanizeLabel(event.lifecycle)}</span></Link>)}</div>
      </section>;
    })}
    {!days.length && <p className="gazette-footnote">No exchange events are reported for this month.</p>}
    <p className="gazette-footnote">Allotment, refund and listing dates use the standard exchange timeline until the exchange reports them.</p>
  </section>;
}
