import Link from "next/link";
import { displayCompanyName, displayDate, priceBand } from "@/lib/format";
import { IpoCardData } from "@/lib/types";
import { StatusPill } from "./status-pill";

export function IpoCard({ ipo, priority = false }: { ipo: IpoCardData; priority?: boolean }) {
  const companyName = displayCompanyName(ipo.company_name);

  return (
    <article className={`ipo-card ${priority ? "ipo-card-featured" : ""}`}>
      <div className="date-rail" aria-label={`Opens ${displayDate(ipo.open_date)}`}>
        <span>{ipo.open_date ? displayDate(ipo.open_date, { month: "short" }) : "TBA"}</span>
        <strong>{ipo.open_date ? new Date(`${ipo.open_date}T00:00:00+05:30`).getDate() : "—"}</strong>
      </div>
      <div className="ipo-card-main">
        <div className="card-kicker">
          <StatusPill status={ipo.lifecycle} />
          <span>{ipo.listings.map((listing) => `${listing.exchange} ${listing.segment === "SME" ? "SME" : ""}`.trim()).join(" · ")}</span>
        </div>
        <h3><Link href={`/ipo/${ipo.slug}`}>{companyName}</Link></h3>
        <dl className="card-facts">
          <div><dt>Price band</dt><dd>{priceBand(ipo.price_low, ipo.price_high)}</dd></div>
          <div><dt>Lot</dt><dd>{ipo.lot_size?.toLocaleString("en-IN") ?? "TBA"}</dd></div>
          <div><dt>Closes</dt><dd>{displayDate(ipo.close_date, { day: "2-digit", month: "short" })}</dd></div>
        </dl>
      </div>
      <Link href={`/ipo/${ipo.slug}`} className="arrow-link" aria-label={`View ${companyName}`}>↗</Link>
    </article>
  );
}
