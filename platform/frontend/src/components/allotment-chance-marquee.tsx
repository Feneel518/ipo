import type { IpoDetailData, Subscription } from "@/lib/types";

type ChanceEstimate = {
  label: string;
  percent: number;
  oneIn: number;
  basis: "applications" | "subscription";
};

const lotteryPoolOrder = ["RETAIL", "INDIVIDUAL", "SNII", "BNII", "EMPLOYEE", "SHAREHOLDER"];
const poolLabels: Record<string, string> = {
  RETAIL: "Retail",
  INDIVIDUAL: "Individual",
  SNII: "sNII",
  BNII: "bNII",
  EMPLOYEE: "Employee",
  SHAREHOLDER: "Shareholder",
};

function positiveNumber(value: string | null | undefined) {
  const number = Number(value);
  return Number.isFinite(number) && number > 0 ? number : null;
}

function estimateChances(ipo: IpoDetailData, latestSubscriptions: Subscription[]): ChanceEstimate[] {
  const subscriptions = new Map(latestSubscriptions.map((row) => [row.category.toUpperCase(), row]));

  // Mainboard issues use RETAIL while some SME records use INDIVIDUAL for the
  // equivalent pool. Avoid showing both names for the same applicant class.
  if (subscriptions.has("RETAIL")) subscriptions.delete("INDIVIDUAL");

  return lotteryPoolOrder.flatMap((category) => {
    const subscription = subscriptions.get(category);
    if (!subscription) return [];

    const pool = ipo.reservation_summary?.rows.find((row) => {
      const poolCategory = row.category.toUpperCase();
      return poolCategory === category
        || (category === "RETAIL" && poolCategory === "INDIVIDUAL")
        || (category === "INDIVIDUAL" && poolCategory === "RETAIL");
    });
    const applications = positiveNumber(subscription.applications);
    const maxAllottees = pool?.max_allottees ?? null;
    const multiple = positiveNumber(subscription.calculated_subscription);

    let rawChance: number | null = null;
    let basis: ChanceEstimate["basis"] = "applications";
    if (applications && maxAllottees && maxAllottees > 0) {
      rawChance = maxAllottees / applications;
    } else if (multiple) {
      rawChance = 1 / multiple;
      basis = "subscription";
    }
    if (rawChance == null) return [];

    const chance = Math.min(1, rawChance);
    return [{
      label: poolLabels[category] ?? category,
      percent: chance * 100,
      oneIn: Math.max(1, Math.round(1 / chance)),
      basis,
    }];
  });
}

function formatPercent(percent: number) {
  return percent.toLocaleString("en-IN", {
    minimumFractionDigits: percent < 1 ? 2 : 1,
    maximumFractionDigits: percent < 1 ? 2 : 1,
  });
}

export function AllotmentChanceMarquee({
  ipo,
  latestSubscriptions,
}: {
  ipo: IpoDetailData;
  latestSubscriptions: Subscription[];
}) {
  const estimates = estimateChances(ipo, latestSubscriptions);
  const messages = estimates.length
    ? estimates.map((estimate) => `${estimate.label} · ${formatPercent(estimate.percent)}% · 1 in ${estimate.oneIn}`)
    : ["Allotment odds · awaiting data"];
  const tickerItems = Array.from({ length: Math.max(8, messages.length * 3) }, (_, index) => messages[index % messages.length]);
  const accessibleMessage = estimates.length
    ? `${estimates.map((estimate) => `Estimated ${estimate.label} allotment chance ${formatPercent(estimate.percent)} percent, or about 1 in ${estimate.oneIn} applications`).join(". ")}. Estimates use ${estimates.some((estimate) => estimate.basis === "applications") ? "reported applications and available lots where available" : "reported subscription multiples"}. Indicative only.`
    : "Allotment odds will appear when exchange application data is available.";

  return (
    <div className={`allotment-marquee ${estimates.length ? "" : "allotment-marquee-pending"}`} role="status" aria-label={accessibleMessage}>
      <div className="allotment-marquee-track" aria-hidden="true">
        {[0, 1].map((group) => (
          <div className="allotment-marquee-group" key={group}>
            {tickerItems.map((message, item) => <span key={item}>{message}</span>)}
          </div>
        ))}
      </div>
    </div>
  );
}
