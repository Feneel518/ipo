"use client";

import type { CSSProperties } from "react";
import { useEffect, useState } from "react";
import { displayDate, indiaDateKey } from "@/lib/format";

type IpoTimetableProps = {
  companyName: string;
  openDate: string | null;
  closeDate: string | null;
  allotmentDate: string | null;
  allotmentDateIsEstimated: boolean;
  refundDate: string | null;
  refundDateIsEstimated: boolean;
  creditDate: string | null;
  creditDateIsEstimated: boolean;
  expectedListingDate: string | null;
  listingDate: string | null;
  initialToday: string;
};

function getTimelineProgress(dates: Array<string | null>, today: string) {
  const todayTime = Date.parse(`${today}T00:00:00+05:30`);
  const points = dates
    .map((date, index) => ({ index, time: date ? Date.parse(`${date}T00:00:00+05:30`) : null }))
    .filter((point): point is { index: number; time: number } => point.time !== null && Number.isFinite(point.time));

  if (!points.length || todayTime < points[0].time) return 0;
  const last = points.at(-1)!;
  if (todayTime >= last.time) return last.index / (dates.length - 1);

  const next = points.find((point) => point.time > todayTime)!;
  const previous = points.findLast((point) => point.time <= todayTime) ?? points[0];
  const elapsed = (todayTime - previous.time) / (next.time - previous.time);
  return (previous.index + ((next.index - previous.index) * elapsed)) / (dates.length - 1);
}

function dateParts(value: string | null) {
  if (!value) return { meta: "Date pending", date: "TBA" };
  return {
    meta: `${displayDate(value, { year: "numeric" })} · ${displayDate(value, { weekday: "long" })}`,
    date: displayDate(value, { day: "2-digit", month: "short" }),
  };
}

export function IpoTimetable({ companyName, openDate, closeDate, allotmentDate, allotmentDateIsEstimated, refundDate, refundDateIsEstimated, creditDate, creditDateIsEstimated, expectedListingDate, listingDate, initialToday }: IpoTimetableProps) {
  const [today, setToday] = useState(initialToday);

  useEffect(() => {
    const syncToday = () => setToday(indiaDateKey());
    syncToday();
    const timer = window.setInterval(syncToday, 60_000);
    document.addEventListener("visibilitychange", syncToday);
    window.addEventListener("focus", syncToday);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", syncToday);
      window.removeEventListener("focus", syncToday);
    };
  }, []);

  const displayedListingDate = listingDate ?? expectedListingDate;
  const milestones = [
    { label: "IPO opens", date: openDate, estimated: false },
    { label: "IPO closes", date: closeDate, estimated: false },
    { label: "Allotment", date: allotmentDate, estimated: allotmentDateIsEstimated },
    { label: "Refunds", date: refundDate, estimated: refundDateIsEstimated },
    { label: "Shares credited", date: creditDate, estimated: creditDateIsEstimated },
    { label: "Listing day", date: displayedListingDate, estimated: !listingDate && Boolean(expectedListingDate) },
  ];
  const milestoneDates = milestones.map((milestone) => milestone.date);
  const progress = getTimelineProgress(milestoneDates, today);
  const knownDates = milestoneDates.filter((date): date is string => Boolean(date));
  const showToday = knownDates.length > 0 && today >= knownDates[0] && today <= knownDates.at(-1)!;
  const timelineStyle = {
    "--timeline-progress": progress,
    "--timeline-position": `${8.333 + (progress * 83.334)}%`,
    "--timeline-position-percent": `${progress * 100}%`,
  } as CSSProperties;

  return (
    <section className="ipo-timetable" aria-labelledby="ipo-timetable-title">
      <header className="ipo-timetable-heading">
        <div>
          <p className="overline">IPO schedule</p>
          <h2 id="ipo-timetable-title">IPO timetable</h2>
        </div>
        <span>{Math.round(progress * 100)}% through schedule</span>
      </header>

      <div className="ipo-timeline-track" style={timelineStyle}>
        <span className="ipo-timeline-progress" role="progressbar" aria-label="IPO schedule progress" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(progress * 100)} />
        {showToday && <span className="ipo-timeline-now" aria-label={`Today, ${displayDate(today)}`}>Today: {dateParts(today).date}</span>}
        <div className="ipo-timeline-range" aria-hidden="true">
          <span><small>Opens</small><strong>{dateParts(openDate).date}</strong></span>
          <span><small>Lists</small><strong>{dateParts(displayedListingDate).date}</strong></span>
        </div>
        <ol className="ipo-timeline" aria-label={`${companyName} IPO timetable`}>
          {milestones.map(({ label, date, estimated }, index) => {
            const parts = dateParts(date);
            const state = !date ? "pending" : date < today ? "complete" : date === today ? "current" : "upcoming";
            return (
              <li className={`ipo-timeline-step is-${state}`} key={label}>
                <span className="ipo-timeline-marker" aria-hidden="true">{String(index + 1).padStart(2, "0")}</span>
                <div>
                  <span>{label}</span>
                  <strong>{parts.date}</strong>
                  <small>{parts.meta}{estimated && <em>Estimated</em>}</small>
                </div>
              </li>
            );
          })}
        </ol>
      </div>

      <p className="ipo-timetable-note">Only dates marked Estimated use the standard exchange timeline. Unmarked dates are exchange-reported.</p>
    </section>
  );
}
