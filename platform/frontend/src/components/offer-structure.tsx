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

const categoryHints: Record<string, string> = {
  RETAIL: "Applications up to ₹2 lakh",
  INDIVIDUAL: "Applications up to ₹2 lakh",
  NII: "Applications above ₹2 lakh",
  BNII: "Large HNI applications",
  SNII: "Small HNI applications",
};

const investorCategories = new Set(["RETAIL", "INDIVIDUAL", "NII", "BNII", "SNII"]);
const institutionalCategories = new Set(["QIB", "ANCHOR", "QIB_EX_ANCHOR"]);

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
  const showAllotmentEstimate = ipo.lifecycle === "OPEN" && Boolean(summary?.rows.some((row) => row.max_allottees != null));
  const allocationRows = summary?.rows.map((row) => {
    const subscription = categorySubscription(subscriptionRows, row.category);
    const applicationCount = Number(subscription?.applications);
    const hasApplicationCount = Number.isFinite(applicationCount) && applicationCount > 0;
    const subscriptionMultiple = Number(subscription?.calculated_subscription);
    const hasSubscriptionMultiple = Number.isFinite(subscriptionMultiple) && subscriptionMultiple > 0;
    const chanceSource = hasApplicationCount ? "applications" : hasSubscriptionMultiple ? "minimum-lot" : null;
    const chance = row.max_allottees != null && chanceSource
      ? Math.min(100, chanceSource === "applications" ? row.max_allottees / applicationCount * 100 : 100 / subscriptionMultiple)
      : null;
    const odds = chance != null && chance < 100 && row.max_allottees
      ? Math.max(2, Math.round(chanceSource === "applications" ? applicationCount / row.max_allottees : subscriptionMultiple))
      : null;

    return { ...row, chance, chanceSource, odds };
  }) ?? [];
  const investorRows = allocationRows.filter((row) => investorCategories.has(row.category));
  const institutionalRows = allocationRows.filter((row) => institutionalCategories.has(row.category));
  const specialRows = allocationRows.filter((row) => !investorCategories.has(row.category) && !institutionalCategories.has(row.category));

  return (
    <section className="offer-structure" aria-labelledby="offer-structure-title">
      <header className="offer-structure-heading">
        <div>
          <p className="overline">Application field guide</p>
          <h2 id="offer-structure-title">One issue.<br /><em>Your way in.</em></h2>
        </div>
        <p>Find the investor category that fits your bid, understand the shares set aside for it, then choose a valid application size.</p>
      </header>

      <div className="application-desk">
        {summary && <article className="allocation-map" aria-labelledby="allocation-map-title">
          <header className="desk-heading">
            <span className="desk-step">01</span>
            <div><p>Choose your lane</p><h3 id="allocation-map-title">Shares reserved for you</h3></div>
          </header>

          <dl className="issue-totals" aria-label="Issue reservation summary">
            <div className="issue-total-primary"><dt>Total issue</dt><dd>{quantity(summary.total_issue_shares)}</dd></div>
            <div><dt>Public book</dt><dd>{quantity(summary.net_offer_shares)}</dd></div>
            <div><dt>Reserved</dt><dd>{quantity(summary.reserved_shares)}</dd></div>
          </dl>

          {investorRows.length > 0 && <div className="investor-lanes" role="list" aria-label="Investor allocation categories">
            {investorRows.map((row, index) => {
              const share = row.percentage_net ?? row.percentage_total;
              return <article className="investor-lane" role="listitem" key={row.category}>
                <div className="lane-index" aria-hidden="true">{String(index + 1).padStart(2, "0")}</div>
                <div className="lane-main">
                  <header>
                    <div><p>{categoryHints[row.category] ?? "Individual investor pool"}</p><h4>{categoryLabel(row.category)}</h4></div>
                    {row.is_derived && <span>Derived</span>}
                  </header>
                  <div className="lane-track" aria-hidden="true"><span style={{ width: `${Math.min(100, Number(share))}%` }} /></div>
                  <dl className="lane-facts">
                    <div><dt>Pool size</dt><dd>{quantity(row.shares)}</dd></div>
                    <div><dt>Possible allottees</dt><dd>{row.max_allottees == null ? "Not reported" : row.max_allottees.toLocaleString("en-IN")}</dd></div>
                  </dl>
                </div>
                <div className="lane-share"><strong>{percent(share)}</strong><span>{row.percentage_net == null ? "issue allocation" : "public-book allocation"}</span></div>
                {showAllotmentEstimate && row.max_allottees != null && <div className={`lane-chance${row.chance == null ? " is-waiting" : ""}`}>
                  <span>Live allotment estimate</span>
                  <strong>{row.chance == null ? "Waiting" : chanceLabel(row.chance)}</strong>
                  <small>{row.chance == null ? "Updates when bids arrive" : row.chance >= 100 ? "Likely with a valid bid" : `About 1 in ${row.odds}${row.chanceSource === "minimum-lot" ? " · bid-based" : ""}`}</small>
                </div>}
              </article>;
            })}
          </div>}

          {(institutionalRows.length > 0 || specialRows.length > 0) && <details className="market-context">
            <summary><span>See the rest of the issue</span><small>Institutional &amp; special pools</small></summary>
            <div className="context-rows" role="list">
              {[...institutionalRows, ...specialRows].map((row) => <div role="listitem" key={row.category}>
                <p><strong>{categoryLabel(row.category)}</strong>{row.parent_category && <small>Inside {categoryLabel(row.parent_category)}</small>}</p>
                <span>{quantity(row.shares)}</span>
                <b>{percent(row.percentage_net ?? row.percentage_total)}</b>
              </div>)}
            </div>
          </details>}

          <footer className="allocation-method"><span>{showAllotmentEstimate ? "Probability = possible allottees ÷ valid applications × 100. If application counts are unavailable, we use 100 ÷ the subscription multiple, assuming minimum-lot bids. Estimates are indicative." : "Allocation percentages show the portion of reported shares reserved for each category; they are not subscription multiples."}</span>{reservationSource && <a href={reservationSource} target="_blank" rel="noreferrer">Verify at source ↗</a>}</footer>
        </article>}

        {applications.length > 0 && <aside className="bid-ticket" aria-labelledby="bid-ticket-title">
          <header className="desk-heading bid-ticket-heading">
            <span className="desk-step">02</span>
            <div><p>Choose your bid</p><h3 id="bid-ticket-title">Valid application sizes</h3></div>
          </header>

          <div className="ticket-price">
            <span>Calculated at</span>
            <strong>{money(ipo.final_issue_price ?? ipo.price_high)}</strong>
            <small>{ipo.final_issue_price ? "Final issue price" : "Upper price band"} · per share</small>
          </div>

          <div className="ticket-options" role="list" aria-label="Minimum and maximum IPO applications">
            {applications.map((row, index) => <article className={`ticket-option ${row.application_kind === "MIN" ? "is-entry" : "is-ceiling"}`} role="listitem" key={`${row.category}-${row.application_kind}`}>
              <span className="ticket-marker" aria-hidden="true">{String(index + 1).padStart(2, "0")}</span>
              <div className="ticket-option-copy">
                <p>{categoryLabel(row.category)}</p>
                <span>{row.application_kind === "MIN" ? "Entry application" : "Category ceiling"}</span>
              </div>
              <strong className="ticket-amount">{money(row.amount)}</strong>
              <dl><div><dt>Lots</dt><dd>{row.lots.toLocaleString("en-IN")}</dd></div><div><dt>Shares</dt><dd>{row.shares.toLocaleString("en-IN")}</dd></div></dl>
            </article>)}
          </div>

          <footer className="ticket-note">Amounts are indicative and exclude any blocked-funds variation.{ipo.platform === "SME" && " SME sizing follows the exchange-reported minimum order quantity."}</footer>
        </aside>}
      </div>
    </section>
  );
}
