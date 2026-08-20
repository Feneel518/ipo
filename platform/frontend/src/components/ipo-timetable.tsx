import type { CSSProperties } from "react";
import { displayDate } from "@/lib/format";

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
  listingDate: string | null;
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
  if (!value) return { weekday: "Date pending", date: "TBA" };
  return {
    weekday: displayDate(value, { weekday: "long" }),
    date: displayDate(value, { day: "2-digit", month: "short", year: "numeric" }),
  };
}

export function IpoTimetable({ companyName, openDate, closeDate, allotmentDate, allotmentDateIsEstimated, refundDate, refundDateIsEstimated, creditDate, creditDateIsEstimated, listingDate }: IpoTimetableProps) {
  const today = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata" }).format(new Date());
  const milestones = [
    { label: "IPO opens", date: openDate, estimated: false },
    { label: "IPO closes", date: closeDate, estimated: false },
    { label: "Allotment", date: allotmentDate, estimated: allotmentDateIsEstimated },
    { label: "Refunds", date: refundDate, estimated: refundDateIsEstimated },
    { label: "Shares credited", date: creditDate, estimated: creditDateIsEstimated },
    { label: "Listing day", date: listingDate, estimated: false },
  ];
  const progress = getTimelineProgress(milestones.map((milestone) => milestone.date), today);
  const timelineStyle = {
    "--timeline-progress": progress,
    "--timeline-position": `${8.333 + (progress * 83.334)}%`,
    "--timeline-position-mobile": `${15 + (progress * 390)}px`,
  } as CSSProperties;

  return (
    <section className="ipo-timetable" aria-labelledby="ipo-timetable-title">
      <header className="ipo-timetable-heading">
        <div>
          <p className="overline">Tentative schedule</p>
          <h2 id="ipo-timetable-title">IPO timetable</h2>
        </div>
        <span>{Math.round(progress * 100)}% through schedule</span>
      </header>

      <div className="ipo-timeline-track" style={timelineStyle}>
        <span className="ipo-timeline-progress" role="progressbar" aria-label="IPO schedule progress" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(progress * 100)} />
        {progress > 0 && progress < 1 && <span className="ipo-timeline-now" aria-label={`Today, ${displayDate(today)}`}>Today</span>}
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
                  <small>{parts.weekday}{estimated ? " · Estimated" : ""}</small>
                </div>
              </li>
            );
          })}
        </ol>
      </div>

      <p className="ipo-timetable-note">Dates marked estimated use the standard exchange timeline until an official date is reported.</p>
    </section>
  );
}
