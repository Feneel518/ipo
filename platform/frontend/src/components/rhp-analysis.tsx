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

export function RhpAnalysis({ analysis, sourceUrl, approvedAt, status }: { analysis: RhpAnalysisData; sourceUrl?: string; approvedAt: string | null; status: "READY" | "APPROVED" | null }) {
  const description = foundText(analysis.company.business_description);
  const industry = foundText(analysis.company.industry);
  const strengths = analysis.company.competitive_strengths.filter(foundText);
  const drivers = analysis.company.growth_drivers.filter(foundText);
  const objects = analysis.ipo.objects_of_issue.filter(foundText);
  const latestFinancial = analysis.financials[0];
  const highlights: Array<[string, RhpNumericFact | undefined, string]> = [
    ["Promoter holding", analysis.promoters.post_issue_holding_pct, "after the issue"],
    ["Customer concentration", analysis.customer_concentration.top_10_customer_revenue_pct, "top 10 customers"],
    ["Total borrowings", latestFinancial?.total_borrowings, latestFinancial?.financial_year ?? "latest reported year"],
  ];
  const visibleHighlights = highlights.filter((item): item is [string, RhpNumericFact, string] => Boolean(item[1] && foundNumber(item[1])));
  const approvedLabel = approvedAt
    ? new Intl.DateTimeFormat("en-IN", { dateStyle: "medium", timeZone: "Asia/Kolkata" }).format(new Date(approvedAt))
    : null;

  return (
    <section className="rhp-analysis" aria-labelledby="rhp-analysis-title">
      <header className="rhp-analysis-heading">
        <div><p className="overline">Inside the prospectus</p><h2 id="rhp-analysis-title">The business,<br /><em>decoded.</em></h2></div>
        <div className="rhp-verification"><span>{status === "APPROVED" ? "Human-approved extraction" : "Validated extraction"}</span><strong>{approvedLabel ?? "Checked against cited RHP pages"}</strong>{sourceUrl && <a href={sourceUrl} target="_blank" rel="noreferrer">Read source RHP ↗</a>}</div>
      </header>

      {(description || industry) && <article className="company-brief">
        <div className="brief-index" aria-hidden="true">01</div>
        <div><p className="overline">Company brief</p>{industry && <span className="industry-tag">{industry}</span>}<h3>What the company does</h3>{description && <p>{description}</p>}
          {analysis.company.products_services.length > 0 && <ul className="product-tags" aria-label="Products and services">{analysis.company.products_services.map((item) => <li key={item}>{item}</li>)}</ul>}
        </div>
        {visibleHighlights.length > 0 && <dl className="rhp-highlights">{visibleHighlights.map(([label, fact, hint]) => <div key={label}><dt>{label}</dt><dd>{numberLabel(fact)}</dd><small>{hint}</small></div>)}</dl>}
      </article>}

      {analysis.financials.length > 0 && <article className="financial-ledger">
        <header><div><span className="brief-index">02</span><p className="overline">Reported financials</p><h3>A multi-year view</h3></div><small>Figures retain the units reported in the RHP</small></header>
        <div className="rhp-table-wrap"><table><thead><tr><th scope="col">Financial year</th>{financialColumns.map(([label]) => <th scope="col" key={label}>{label}</th>)}</tr></thead><tbody>{analysis.financials.map((period) => <tr key={period.financial_year}><th scope="row">{period.financial_year}</th>{financialColumns.map(([label, key]) => <td data-label={label} key={key}>{numberLabel(period[key])}</td>)}</tr>)}</tbody></table></div>
      </article>}

      {(objects.length > 0 || strengths.length > 0 || drivers.length > 0) && <div className="rhp-thesis-grid">
        {objects.length > 0 && <article><span className="thesis-number">03 / use of funds</span><h3>Where the money goes</h3><ol>{objects.map((fact, index) => <li key={`${fact.value}-${index}`}><span>{String(index + 1).padStart(2, "0")}</span><p>{fact.value}<small>{sourcePage(fact)}</small></p></li>)}</ol></article>}
        {(strengths.length > 0 || drivers.length > 0) && <article className="growth-case"><span className="thesis-number">04 / growth case</span><h3>What could drive the business</h3><ul>{[...strengths, ...drivers].slice(0, 8).map((fact, index) => <li key={`${fact.value}-${index}`}><span aria-hidden="true">↗</span><p>{fact.value}<small>{sourcePage(fact)}</small></p></li>)}</ul></article>}
      </div>}

      {analysis.risks.length > 0 && <article className="rhp-risks">
        <header><div><span className="brief-index">05</span><p className="overline">Risk factors</p><h3>Read the downside first</h3></div><p>Selected material risks disclosed in the RHP. This is a summary, not a substitute for the prospectus.</p></header>
        <div className="risk-register">{analysis.risks.map((risk, index) => <details key={`${risk.title}-${index}`} open={index === 0}><summary><span>{String(index + 1).padStart(2, "0")}</span><div><small>{risk.category.replaceAll("_", " ")}</small><strong>{risk.title}</strong></div><i aria-hidden="true">+</i></summary><p>{risk.description}</p></details>)}</div>
      </article>}
    </section>
  );
}
