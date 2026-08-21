import type { IpoDetailData, Subscription } from "@/lib/types";
import { humanizeLabel, money, quantity } from "@/lib/format";

const categoryLabels: Record<string, string> = {
  QIB: "Qualified institutional buyers",
  ANCHOR: "Anchor investors",
  QIB_EX_ANCHOR: "QIB excluding anchor",
  NII: "Non-institutional investors",
  BNII: "bNII · above ₹10 lakh",
  SNII: "sNII · ₹2–10 lakh",
  RETAIL: "Retail investors",
  INDIVIDUAL: "Individual investors",
  EMPLOYEE: "Employee reservation",
  SHAREHOLDER: "Shareholder reservation",
  MARKET_MAKER: "Market maker reservation",
};

function percent(value: string | null) {
  if (value == null) return "—";
  return `${new Intl.NumberFormat("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(Number(value))}%`;
}

function categoryLabel(value: string) {
  return categoryLabels[value] ?? humanizeLabel(value);
}

function chanceLabel(value: number) {
  if (value < 0.1) return "<0.1%";
  if (value < 10) return `${value.toFixed(1)}%`;
  return `${Math.round(value)}%`;
}

function categorySubscription(rows: Map<string, Subscription>, category: string) {
  return rows.get(category)
    ?? (category === "RETAIL" ? rows.get("INDIVIDUAL") : undefined)
    ?? (category === "INDIVIDUAL" ? rows.get("RETAIL") : undefined);
}

export function OfferStructure({ ipo, latestSubscriptions = [] }: { ipo: IpoDetailData; latestSubscriptions?: Subscription[] }) {
  const summary = ipo.reservation_summary ?? null;
  const applications = ipo.lot_size_applications ?? [];
  if (!summary && applications.length === 0) return null;

  const reservationSource = summary?.rows.find((row) => row.source_url)?.source_url;
  const subscriptionRows = new Map(latestSubscriptions.map((row) => [row.category, row]));
  const showAllotmentEstimate = ipo.lifecycle === "OPEN" && Boolean(
    summary?.rows.some((row) => row.max_allottees != null),
  );
  const allocationRows = summary?.rows.map((row) => {
    const subscription = categorySubscription(subscriptionRows, row.category);
    const applicationCount = Number(subscription?.applications);
    const hasApplicationCount = Number.isFinite(applicationCount) && applicationCount > 0;
    const subscriptionMultiple = Number(subscription?.calculated_subscription);
    const hasSubscriptionMultiple = Number.isFinite(subscriptionMultiple) && subscriptionMultiple > 0;
    const chanceSource = hasApplicationCount ? "applications" : hasSubscriptionMultiple ? "minimum-lot" : null;
    const chance = row.max_allottees != null && chanceSource
      ? Math.min(100, chanceSource === "applications"
        ? row.max_allottees / applicationCount * 100
        : 100 / subscriptionMultiple)
      : null;
    const odds = chance != null && chance < 100 && row.max_allottees
      ? Math.max(2, Math.round(chanceSource === "applications"
        ? applicationCount / row.max_allottees
        : subscriptionMultiple))
      : null;

    return { ...row, chance, chanceSource, odds };
  }) ?? [];

  return (
    <section className="offer-structure" aria-labelledby="offer-structure-title">
      <header className="offer-structure-heading">
        <div>
          <p className="overline">Application map</p>
          <h2 id="offer-structure-title">How the shares<br /><em>are split.</em></h2>
        </div>
        <p>Read the offer category by category—how many shares sit in each pool, who can access them, and the live allotment odds where they can be estimated.</p>
      </header>

      {summary && <div className="reservation-panel">
        <div className="allocation-snapshot" aria-label="Issue reservation summary">
          <div className="allocation-snapshot-primary"><span>Issue inventory</span><strong>{quantity(summary.total_issue_shares)}</strong><small>Total shares on offer</small></div>
          <div><span>Public book</span><strong>{quantity(summary.net_offer_shares)}</strong><small>Net offer shares</small></div>
          <div><span>Special pools</span><strong>{quantity(summary.reserved_shares)}</strong><small>Reserved shares</small></div>
        </div>
        <div className="allocation-ledger" role="list" aria-label="Investor category allocation">
          {allocationRows.map((row, index) => <article className={`allocation-row${row.parent_category ? " is-child" : ""}`} role="listitem" key={row.category}>
            <span className="allocation-index" aria-hidden="true">{String(index + 1).padStart(2, "0")}</span>
            <header className="allocation-identity">
              <small>{row.parent_category ? `Inside ${categoryLabel(row.parent_category)}` : "Investor allocation"}</small>
              <h3>{categoryLabel(row.category)}</h3>
              {row.is_derived && <span>Derived allocation</span>}
            </header>
            <dl className="allocation-facts">
              <div><dt>Shares in pool</dt><dd>{quantity(row.shares)}</dd></div>
              <div><dt>Maximum allottees</dt><dd>{row.max_allottees == null ? "Not applicable" : row.max_allottees.toLocaleString("en-IN")}</dd></div>
            </dl>
            {showAllotmentEstimate && <div className={`allocation-odds${row.max_allottees == null ? " is-muted" : row.chance != null && row.chance >= 100 ? " is-likely" : ""}`}>
              <span>Live allotment estimate</span>
              {row.max_allottees == null ? <><strong>Different method</strong><small>No lottery-style estimate</small></> : row.chance == null ? <><strong>Unavailable</strong><small>Waiting for bid data</small></> : row.chance >= 100 ? <><strong>Likely</strong><small>Subject to a valid bid</small></> : <><strong>{chanceLabel(row.chance)}</strong><small>About 1 in {row.odds}{row.chanceSource === "minimum-lot" ? " · bid-based" : ""}</small></>}
            </div>}
            <div className="allocation-share">
              <div className="allocation-meter" aria-hidden="true"><span style={{ width: `${Math.min(100, Number(row.percentage_total))}%` }} /></div>
              <dl><div><dt>Of net offer</dt><dd>{percent(row.percentage_net)}</dd></div><div><dt>Of total issue</dt><dd>{percent(row.percentage_total)}</dd></div></dl>
            </div>
          </article>)}
        </div>
        <footer><span>{showAllotmentEstimate ? "Uses live application counts when reported; otherwise 100 ÷ subscription on a minimum-lot basis. Preliminary, not guaranteed." : "Percentages are calculated from stored share quantities."}</span>{reservationSource && <a href={reservationSource} target="_blank" rel="noreferrer">Official source ↗</a>}</footer>
      </div>}

      {applications.length > 0 && <div className="lot-panel">
        <header className="lot-panel-heading"><div><span>Application ladder</span><h3>Build your bid.</h3><p>From the smallest valid order to each category ceiling.</p></div><div className="lot-price"><span>Calculation price</span><strong>{money(ipo.final_issue_price ?? ipo.price_high)}</strong><small>{ipo.final_issue_price ? "Final price" : "Upper price band"} · per share</small></div></header>
        <div className="lot-ladder" role="list" aria-label="Minimum and maximum IPO applications">
          {applications.map((row, index) => <article className="lot-card" role="listitem" key={`${row.category}-${row.application_kind}`}>
            <header><span>{String(index + 1).padStart(2, "0")}</span><small>{row.application_kind === "MIN" ? "Entry bid" : "Category ceiling"}</small></header>
            <div className="lot-card-category"><span>{categoryLabel(row.category)}</span><b>{row.application_kind === "MIN" ? "Minimum" : "Maximum"}</b></div>
            <strong className="lot-card-amount">{money(row.amount)}</strong>
            <dl><div><dt>Lots</dt><dd>{row.lots.toLocaleString("en-IN")}</dd></div><div><dt>Shares</dt><dd>{row.shares.toLocaleString("en-IN")}</dd></div></dl>
          </article>)}
        </div>
        {ipo.platform === "SME" && <p className="lot-rule-note">SME application size follows the minimum order quantity reported by the exchange; mainboard retail/HNI thresholds are not applied.</p>}
      </div>}
    </section>
  );
}
