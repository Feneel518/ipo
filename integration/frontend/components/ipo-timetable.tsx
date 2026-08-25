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
  expectedListingDate: string | null;
  listingDate: string | null;
};

function dateLabel(value: string | null) {
  if (!value) return "Not yet reported";
  return `${displayDate(value, { day: "numeric", month: "short", year: "numeric" })} · ${displayDate(value, { weekday: "long" })}`;
}

export function IpoTimetable({ companyName, openDate, closeDate, allotmentDate, allotmentDateIsEstimated, refundDate, refundDateIsEstimated, creditDate, creditDateIsEstimated, expectedListingDate, listingDate }: IpoTimetableProps) {
  const displayedListingDate = listingDate ?? expectedListingDate;
  const milestones = [
    { label: "IPO opens", date: openDate, estimated: false },
    { label: "IPO closes", date: closeDate, estimated: false },
    { label: "Allotment", date: allotmentDate, estimated: allotmentDateIsEstimated },
    { label: "Refunds", date: refundDate, estimated: refundDateIsEstimated },
    { label: "Shares credited", date: creditDate, estimated: creditDateIsEstimated },
    { label: "Listing day", date: displayedListingDate, estimated: !listingDate && Boolean(expectedListingDate) },
  ];

  return (
    <section aria-label={`${companyName} IPO timetable`}>
      <div className="column-heading"><span>IPO timetable</span></div>
      {milestones.map(({ label, date, estimated }, index) => (
        <div className="timetable-row" key={label}>
          <span>{String(index + 1).padStart(2, "0")}</span>
          <span>{label}</span>
          <span>{dateLabel(date)}{estimated && <em>Estimated</em>}</span>
        </div>
      ))}
      <p className="gazette-footnote">Only dates marked estimated use the standard exchange timeline. Unmarked dates are exchange-reported.</p>
    </section>
  );
}
