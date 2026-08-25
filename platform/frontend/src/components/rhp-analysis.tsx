import type { RhpAnalysis as RhpAnalysisData, RhpNumericFact, RhpTextFact } from "@/lib/types";

const financialColumns = [
  ["Revenue", "revenue_from_operations"],
  ["Profit after tax", "profit_after_tax"],
  ["Operating cash flow", "operating_cash_flow"],
  ["Borrowings", "total_borrowings"],
  ["Net worth", "total_equity"],
] as const;

function foundText(fact: RhpTextFact) {
  return fact.status === "FOUND" ? fact.value : null;
}

function foundNumber(fact: RhpNumericFact) {
  return fact.status === "FOUND" && fact.value != null ? fact : null;
}

function numberLabel(fact: RhpNumericFact) {
  if (!foundNumber(fact)) return "—";
  const value = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2 }).format(fact.value!);
  if (fact.unit === "PERCENT") return `${value}%`;
  if (fact.unit === "RATIO") return `${value}×`;
  if (fact.unit === "SHARES") return `${value} shares`;
  if (fact.unit === "INR_CRORE") return `₹${value} cr`;
  if (fact.unit === "INR_LAKH") return `₹${value} lakh`;
  if (fact.unit === "INR_MILLION") return `₹${value} mn`;
  if (fact.unit === "INR") return `₹${value}`;
  return value;
}

function sourcePage(fact: RhpTextFact | RhpNumericFact) {
  const source = fact.sources?.[0];
  if (!source) return null;
  return source.document_page_label ? `RHP p. ${source.document_page_label}` : source.pdf_page ? `PDF p. ${source.pdf_page}` : null;
}

export function RhpAnalysis({ analysis }: { analysis: RhpAnalysisData }) {
  const strengths = analysis.company.competitive_strengths.filter(foundText);
  const drivers = analysis.company.growth_drivers.filter(foundText);
  const objects = analysis.ipo.objects_of_issue.filter(foundText);
  const growth = [...strengths, ...drivers].slice(0, 8);

  return (
    <section className="dossier" aria-labelledby="dossier-title">
      <p className="gazette-kicker">Prospectus dossier</p>
      <div className="dossier-heading">
        <h2 id="dossier-title">Numbers, plans <em>&amp; pressure points</em></h2>
        <p>A focused reading of the company&apos;s reported financials, planned use of proceeds, business strengths and material risks.</p>
      </div>

      {analysis.financials.length > 0 && <article className="ledger">
        <header>
          <h3>A multi-year view</h3>
          <small>Figures retain the units reported in the RHP</small>
        </header>
        <table>
          <thead><tr><th scope="col">Fiscal year</th>{financialColumns.map(([label]) => <th scope="col" key={label}>{label}</th>)}</tr></thead>
          <tbody>{analysis.financials.map((period) => <tr key={period.financial_year}>
            <th scope="row">{period.financial_year}</th>
            {financialColumns.map(([label, key]) => <td data-label={label} key={key}>{numberLabel(period[key])}</td>)}
          </tr>)}</tbody>
        </table>
      </article>}

      {(objects.length > 0 || growth.length > 0) && <section className="dossier-briefs" aria-label="Use of funds and growth case">
        <div className="briefs-grid">
          {objects.length > 0 && <article className="funds-brief">
            <header className="brief-heading">
              <div>
                <p className="section-folio"><span>01</span> Use of funds</p>
                <h3>Where the<br /><em>money goes.</em></h3>
              </div>
              <p className="brief-stat" aria-label={`${objects.length} stated ${objects.length === 1 ? "object" : "objects"} in the filing`}>
                <strong>{String(objects.length).padStart(2, "0")}</strong>
                <span>stated {objects.length === 1 ? "object" : "objects"}<br />in the filing</span>
              </p>
            </header>
            <ol>{objects.map((fact, index) => <li className="funds-row" key={`${fact.value}-${index}`}>
              <span aria-hidden="true">{String(index + 1).padStart(2, "0")}</span>
              <p>{fact.value}<small>{sourcePage(fact)}</small></p>
            </li>)}</ol>
          </article>}
          {growth.length > 0 && <article className="growth-brief">
            <header className="brief-heading">
              <div>
                <p className="section-folio"><span>02</span> Growth case</p>
                <h3>What could drive<br /><em>the business.</em></h3>
              </div>
              <p className="brief-stat" aria-label={`${growth.length} signals in the filing`}>
                <strong>{String(growth.length).padStart(2, "0")}</strong>
                <span>signals found<br />in the filing</span>
              </p>
            </header>
            <ul>{growth.map((fact, index) => <li className="strength-row" key={`${fact.value}-${index}`}>
              <span aria-hidden="true">{String(index + 1).padStart(2, "0")}</span>
              <p>{fact.value}<small>{sourcePage(fact)}</small></p>
            </li>)}</ul>
          </article>}
        </div>
      </section>}

      {analysis.risks.length > 0 && <section className="risks" aria-labelledby="risks-title">
        <header>
          <div>
            <p className="risk-kicker"><span>03</span> Risk factors</p>
            <h3 id="risks-title">Read the downside <em>first.</em></h3>
          </div>
          <aside><strong>{String(analysis.risks.length).padStart(2, "0")}</strong><span>material risks<br />selected from the RHP</span></aside>
        </header>
        <p className="risk-deck">Selected material risks disclosed in the RHP. Read these before the upside case. This summary is not a substitute for the prospectus.</p>
        <div className="risk-grid">{analysis.risks.map((risk, index) => <article className={`risk-row${index === 0 ? " risk-row--lead" : ""}`} key={`${risk.title}-${index}`}>
          <span className="risk-number">{String(index + 1).padStart(2, "0")}</span>
          <div className="risk-copy"><small>{risk.category.replaceAll("_", " ")}</small><h4>{risk.title}</h4><p>{risk.description}</p></div>
        </article>)}</div>
      </section>}
    </section>
  );
}

export function CompanyOverview({ analysis, sourceUrl, approvedAt, status }: { analysis: RhpAnalysisData; sourceUrl?: string; approvedAt: string | null; status: "READY" | "APPROVED" | null }) {
  const description = foundText(analysis.company.business_description);
  const industry = foundText(analysis.company.industry);
  const latestFinancial = analysis.financials[0];
  const latestFiscalYear = latestFinancial?.financial_year
    ? `Fiscal ${latestFinancial.financial_year.replace(/^(?:FY|Fiscal)\s*/i, "")}`
    : "latest reported year";
  const highlights: Array<[string, RhpNumericFact | undefined, string]> = [
    ["Customer concentration", analysis.customer_concentration.top_10_customer_revenue_pct, "top 10 customers"],
    ["Total borrowings", latestFinancial?.total_borrowings, latestFiscalYear],
  ];
  const visibleHighlights = highlights
    .filter((item): item is [string, RhpNumericFact, string] => Boolean(item[1] && foundNumber(item[1])))
    .slice(0, 2);
  const approvedLabel = approvedAt
    ? new Intl.DateTimeFormat("en-IN", { dateStyle: "medium", timeZone: "Asia/Kolkata" }).format(new Date(approvedAt))
    : null;
  const products = analysis.company.products_services.slice(0, 8);
  if (!description && !industry && products.length === 0) return null;

  return (
    <section className="glance-panel" aria-labelledby="glance-title">
      <div className="glance-summary">
        <p className="overline">Company at a glance · {status === "APPROVED" ? "Human reviewed" : "RHP validated"}{approvedLabel ? ` · ${approvedLabel}` : ""}</p>
        <h2 id="glance-title">The business, <em>in brief</em></h2>
        {description && <p>{description}</p>}
        {visibleHighlights.length > 0 && <dl className="glance-stats">
          {visibleHighlights.map(([label, fact, hint]) => <div key={label}>
            <dt>{label}</dt><dd>{numberLabel(fact)}</dd><small>{hint}</small>
          </div>)}
        </dl>}
      </div>
      <div className="glance-details">
        {products.length > 0 && <div className="glance-products">
          <span>Products &amp; services</span>
          <ol>{products.map((item) => <li key={item}>{item}</li>)}</ol>
          {analysis.company.products_services.length > products.length && <small>+{analysis.company.products_services.length - products.length} more in the RHP</small>}
        </div>}
      </div>
      <span className="glance-source">{industry ?? "Sector not reported"}{sourceUrl ? " · " : ""}{sourceUrl && <a href={sourceUrl} target="_blank" rel="noreferrer">verify in the RHP ↗</a>}</span>
    </section>
  );
}
