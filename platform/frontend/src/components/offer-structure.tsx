import type { IpoDetailData } from "@/lib/types";
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

export function OfferStructure({ ipo }: { ipo: IpoDetailData }) {
  const summary = ipo.reservation_summary ?? null;
  const applications = ipo.lot_size_applications ?? [];
  if (!summary && applications.length === 0) return null;

  const reservationSource = summary?.rows.find((row) => row.source_url)?.source_url;

  return (
    <section className="offer-structure" aria-labelledby="offer-structure-title">
      <header className="offer-structure-heading">
        <div>
          <p className="overline">Application map</p>
          <h2 id="offer-structure-title">Who the issue is for.</h2>
        </div>
        <p>Official reserved-share quantities, paired with application sizes calculated at the cap price.</p>
      </header>

      {summary && <div className="reservation-panel">
        <div className="offer-summary" aria-label="Issue reservation summary">
          <div><span>Total issue</span><strong>{quantity(summary.total_issue_shares)}</strong><small>shares</small></div>
          <div><span>Net offer</span><strong>{quantity(summary.net_offer_shares)}</strong><small>public allocation</small></div>
          <div><span>Reserved</span><strong>{quantity(summary.reserved_shares)}</strong><small>special portions</small></div>
        </div>
        <div className="offer-table-wrap">
          <table className="offer-table">
            <caption>Investor category reservation</caption>
            <thead><tr><th scope="col">Investor category</th><th scope="col">Shares</th><th scope="col">% net</th><th scope="col">% total</th><th scope="col">Max allottees</th></tr></thead>
            <tbody>
              {summary.rows.map((row) => <tr className={row.parent_category ? "is-child" : undefined} key={row.category}>
                <th scope="row"><span>{row.parent_category ? "↳" : ""}</span>{categoryLabel(row.category)}{row.is_derived && <small>derived</small>}</th>
                <td>{quantity(row.shares)}</td>
                <td>{percent(row.percentage_net)}</td>
                <td>{percent(row.percentage_total)}</td>
                <td>{row.max_allottees == null ? "—" : row.max_allottees.toLocaleString("en-IN")}</td>
              </tr>)}
            </tbody>
          </table>
        </div>
        <footer><span>Percentages are calculated from stored share quantities.</span>{reservationSource && <a href={reservationSource} target="_blank" rel="noreferrer">Official source ↗</a>}</footer>
      </div>}

      {applications.length > 0 && <div className="lot-panel">
        <header><div><span>Bid geometry</span><h3>IPO lot size</h3></div><p>Amounts use {ipo.final_issue_price ? "the final issue price" : "the upper price band"} of <strong>{money(ipo.final_issue_price ?? ipo.price_high)}</strong> per share.</p></header>
        <div className="offer-table-wrap">
          <table className="offer-table lot-table">
            <caption>Minimum and maximum IPO applications</caption>
            <thead><tr><th scope="col">Application</th><th scope="col">Lots</th><th scope="col">Shares</th><th scope="col">Amount</th></tr></thead>
            <tbody>{applications.map((row) => <tr key={`${row.category}-${row.application_kind}`}>
              <th scope="row">{categoryLabel(row.category)} <small>({row.application_kind === "MIN" ? "Min" : "Max"})</small></th>
              <td>{row.lots.toLocaleString("en-IN")}</td>
              <td>{row.shares.toLocaleString("en-IN")}</td>
              <td>{money(row.amount)}</td>
            </tr>)}</tbody>
          </table>
        </div>
        {ipo.platform === "SME" && <p className="lot-rule-note">SME application size follows the minimum order quantity reported by the exchange; mainboard retail/HNI thresholds are not applied.</p>}
      </div>}
    </section>
  );
}
