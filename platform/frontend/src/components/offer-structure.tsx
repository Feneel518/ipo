import type { IpoDetailData, Subscription } from "@/lib/types";
import { humanizeLabel, money, quantity } from "@/lib/format";

const categoryLabels: Record<string, string> = {
  QIB: "Qualified institutional",
  ANCHOR: "Anchor investors",
  QIB_EX_ANCHOR: "QIB excluding anchor",
  NII: "Non-institutional",
  BNII: "bNII",
  SNII: "sNII",
  RETAIL: "Retail investors",
  INDIVIDUAL: "Individual investors",
  EMPLOYEE: "Employee",
  SHAREHOLDER: "Shareholder",
  MARKET_MAKER: "Market maker",
};

const categoryHints: Record<string, string> = {
  RETAIL: "Applications up to ₹2 lakh",
  INDIVIDUAL: "SME individual application",
  NII: "Applications above ₹2 lakh",
  BNII: "Above ₹10 lakh",
  SNII: "₹2 – 10 lakh",
  QIB: "QIB book",
  EMPLOYEE: "Reservation",
  SHAREHOLDER: "Reservation",
  MARKET_MAKER: "Reservation",
};

const poolOrder = ["RETAIL", "INDIVIDUAL", "NII", "BNII", "SNII", "QIB", "ANCHOR", "QIB_EX_ANCHOR", "EMPLOYEE", "SHAREHOLDER", "MARKET_MAKER"];

function percent(value: string | null) {
  if (value == null) return "—";
  return `${new Intl.NumberFormat("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(Number(value))}%`;
}

function categoryLabel(value: string) {
  return categoryLabels[value] ?? humanizeLabel(value);
}

function chanceLabel(value: number) {
  if (value < 0.01) return `${value.toPrecision(1)}%`;
  if (value < 0.1) return `${value.toFixed(2)}%`;
  if (value < 10) return `${value.toFixed(1)}%`;
  return `${Math.round(value)}%`;
}

function oddsLabel(value: number) {
  return value < 2 ? value.toFixed(1) : Math.round(value).toLocaleString("en-IN");
}

function categorySubscription(rows: Map<string, Subscription>, category: string) {
  return rows.get(category)
    ?? (category === "RETAIL" ? rows.get("INDIVIDUAL") : undefined)
    ?? (category === "INDIVIDUAL" ? rows.get("RETAIL") : undefined);
}

/* Left column of the record: valid application sizes. */
export function ApplicationSizes({ ipo }: { ipo: IpoDetailData }) {
  const applications = ipo.lot_size_applications ?? [];
  if (!applications.length) return null;
  const upper = money(ipo.final_issue_price ?? ipo.price_high);

  return (
    <section className="record-section record-table-section" aria-label="Valid application sizes">
      <div className="column-heading"><span>Valid application sizes</span></div>
      {applications.map((row) => (
        <div className="appsize-row" key={`${row.category}-${row.application_kind}`}>
          <span>{categoryLabel(row.category)} <em>{row.application_kind === "MIN" ? "entry" : "ceiling"}</em></span>
          <span>{row.lots.toLocaleString("en-IN")} lots · {row.shares.toLocaleString("en-IN")} sh</span>
          <span>{money(row.amount)}</span>
        </div>
      ))}
      <p className="gazette-footnote">Calculated at {ipo.final_issue_price ? "the final issue price" : "the upper band"} of {upper} per share. Amounts exclude blocked-funds variation.</p>
    </section>
  );
}

/* Full-width section of the record: category reservation breakdown. */
export function ReservedPools({ ipo, latestSubscriptions = [] }: { ipo: IpoDetailData; latestSubscriptions?: Subscription[] }) {
  const summary = ipo.reservation_summary ?? null;
  if (!summary || !summary.rows.length) return null;

  const subscriptionRows = new Map(latestSubscriptions.map((row) => [row.category, row]));
  const showAllotmentEstimate = ipo.lifecycle === "OPEN" && summary.rows.some((row) => row.max_allottees != null);

  const rows = summary.rows.map((row) => {
    const subscription = categorySubscription(subscriptionRows, row.category);
    const applicationCount = Number(subscription?.applications);
    const hasApplicationCount = Number.isFinite(applicationCount) && applicationCount > 0;
    const rawBidQuantity = Number(subscription?.raw_exchange_bid_quantity);
    const hasRawBidQuantity = Number.isFinite(rawBidQuantity) && rawBidQuantity > 0;
    const subscriptionMultiple = Number(subscription?.calculated_subscription);
    const hasSubscriptionMultiple = Number.isFinite(subscriptionMultiple) && subscriptionMultiple > 0;
    const minimumBidQuantity = Number(row.minimum_bid_quantity);
    const hasMinimumBidQuantity = Number.isFinite(minimumBidQuantity) && minimumBidQuantity > 0;
    const maximumApplicationCountRaw = hasMinimumBidQuantity
      ? hasRawBidQuantity
        ? rawBidQuantity / minimumBidQuantity
        : hasSubscriptionMultiple
          ? Number(row.shares) * subscriptionMultiple / minimumBidQuantity
          : null
      : null;
    const maximumApplicationCount = maximumApplicationCountRaw != null ? Math.floor(maximumApplicationCountRaw) : null;
    const chanceSource = hasApplicationCount
      ? "applications"
      : maximumApplicationCount != null && maximumApplicationCount > 0
        ? "bid-volume-floor"
        : null;
    const chance = row.max_allottees != null && chanceSource
      ? Math.min(100, row.max_allottees / (chanceSource === "applications" ? applicationCount : maximumApplicationCount!) * 100)
      : null;
    const odds = chance != null && chance < 100 && row.max_allottees
      ? (chanceSource === "applications" ? applicationCount : maximumApplicationCount!) / row.max_allottees
      : null;
    return { ...row, chance, chanceSource, odds };
  }).sort((left, right) => poolOrder.indexOf(left.category) - poolOrder.indexOf(right.category));

  const estimate = (row: (typeof rows)[number]) => {
    if (!showAllotmentEstimate || row.max_allottees == null) return "Not available yet";
    if (row.chance == null) return "Updates when bids arrive";
    const prefix = row.chanceSource === "bid-volume-floor" ? "At least " : "";
    if (row.chance >= 100) return `${prefix}100% · likely with a valid bid`;
    return `${prefix}${chanceLabel(row.chance)} · about 1 in ${oddsLabel(row.odds!)}`;
  };

  return (
    <section className="pools" aria-label="Shares reserved by category">
      <p className="gazette-kicker">Application field guide</p>
      <h2>Who gets how many shares</h2>
      <p className="pools-intro">The IPO is split into separate pools for each investor category. Find the category you can apply under to see its size and estimated allotment chance.</p>
      <div className="pools-head">
        <span>Category</span><span>Pool size</span><span>Allottees</span><span>Allocation</span><span>Live estimate</span>
      </div>
      {rows.map((row) => (
        <div className="pools-row" key={row.category}>
          <div className="pool-category"><strong>{categoryLabel(row.category)}</strong><small>{categoryHints[row.category] ?? (row.is_derived ? "Derived" : "")}</small></div>
          <div className="pool-metric"><small>Pool size</small><span>{quantity(row.shares)} shares</span></div>
          <div className="pool-metric"><small>Possible allottees</small><span>{row.max_allottees == null ? "Not reported" : row.max_allottees.toLocaleString("en-IN")}</span></div>
          <div className="pool-metric"><small>Share of offer</small><span>{percent(row.percentage_net ?? row.percentage_total)} of {row.percentage_net == null ? "issue" : "public book"}</span></div>
          <div className="pool-metric pool-estimate"><small>Estimated chance</small><span>{estimate(row)}</span></div>
        </div>
      ))}
      <p className="gazette-footnote">Estimate is possible allottees divided by applications. Where the exchange omits application counts, the floor assumes every bid used that category&apos;s minimum bid size. Final odds depend on valid applications and the basis of allotment.</p>
    </section>
  );
}
