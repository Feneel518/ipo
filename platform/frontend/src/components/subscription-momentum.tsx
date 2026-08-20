"use client";

import { Grid } from "@/components/charts/grid";
import { Line, LineChart } from "@/components/charts/line-chart";
import { ChartTooltip } from "@/components/charts/tooltip";
import { XAxis } from "@/components/charts/x-axis";
import type { Subscription } from "@/lib/types";

const chartCategories = ["TOTAL", "RETAIL", "NII", "QIB"] as const;
const categoryLabels: Record<string, string> = {
  TOTAL: "Total",
  RETAIL: "Retail",
  NII: "NII",
  QIB: "QIB",
};

const categoryColors: Record<string, string> = {
  TOTAL: "var(--ink)",
  RETAIL: "var(--orange)",
  NII: "var(--green)",
  QIB: "#76518b",
};

function checkpointLabel(value: string) {
  return new Intl.DateTimeFormat("en-IN", {
    day: "numeric",
    month: "short",
    hour: "numeric",
    minute: "2-digit",
    timeZone: "Asia/Kolkata",
  }).format(new Date(value));
}

function quantityLabel(value: number) {
  return new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2 }).format(value);
}

interface SubscriptionMomentumProps {
  subscriptions: Subscription[];
  exchange?: Subscription["exchange"];
  scope?: Subscription["bid_data_scope"];
}

export function SubscriptionMomentum({ subscriptions, exchange, scope }: SubscriptionMomentumProps) {
  const revisions = subscriptions
    .filter((item) =>
      item.exchange === exchange
      && item.bid_data_scope === scope
      && item.calculated_subscription != null
      && Number.isFinite(Number(item.calculated_subscription))
    )
    .sort((left, right) => Date.parse(right.observed_at) - Date.parse(left.observed_at));

  const latestRevision = new Map<string, Subscription>();
  for (const item of revisions) {
    const key = `${item.captured_at}:${item.category}`;
    if (!latestRevision.has(key)) latestRevision.set(key, item);
  }

  const checkpointMap = new Map<string, Map<string, number>>();
  for (const item of latestRevision.values()) {
    const checkpoint = checkpointMap.get(item.captured_at) ?? new Map<string, number>();
    checkpoint.set(item.category, Number(item.calculated_subscription));
    checkpointMap.set(item.captured_at, checkpoint);
  }

  const checkpoints = [...checkpointMap.entries()]
    .sort(([left], [right]) => Date.parse(left) - Date.parse(right))
    .map(([capturedAt, values]) => ({ capturedAt, values }));
  const categories = chartCategories.filter((category) =>
    checkpoints.some((checkpoint) => checkpoint.values.has(category))
  );

  if (!checkpoints.length || !categories.length) return null;

  const chartData = checkpoints.map((checkpoint) => ({
    date: new Date(checkpoint.capturedAt),
    ...Object.fromEntries(categories.map((category) => [category, checkpoint.values.get(category) ?? 0])),
  }));
  const tableCheckpoints = checkpoints.slice(-8).reverse();

  return (
    <section className="momentum" aria-labelledby="momentum-title">
      <div className="momentum-heading">
        <div>
          <p className="overline">History retained</p>
          <h3 id="momentum-title">Subscription momentum</h3>
        </div>
        <p><strong>{checkpoints.length}</strong> {checkpoints.length === 1 ? "checkpoint" : "checkpoints"}<span>{exchange} · {scope === "ALL_EXCHANGES" ? "All exchanges" : "Reported book"}</span></p>
      </div>

      <div className="momentum-legend" aria-label="Chart legend">
        {categories.map((category) => <span className={`momentum-key key-${category.toLowerCase()}`} key={category}>{categoryLabels[category]}</span>)}
      </div>

      <div className="momentum-chart" role="img" aria-label={`${categories.map((category) => categoryLabels[category]).join(", ")} subscription multiples across ${checkpoints.length} stored exchange checkpoints`}>
        <LineChart data={chartData} xDataKey="date" aspectRatio="16 / 7" margin={{ top: 24, right: 28, bottom: 50, left: 28 }}>
          <Grid horizontal stroke="var(--rule)" strokeDasharray="3,7" />
          {categories.map((category) => <Line
            dataKey={category}
            fadeEdges={false}
            key={category}
            showMarkers
            stroke={categoryColors[category]}
            strokeWidth={category === "TOTAL" ? 4 : 3}
          />)}
          <XAxis numTicks={Math.min(5, checkpoints.length)} tickMode="data" />
          <ChartTooltip
            dotVariant="ring"
            indicatorColor="var(--ink)"
            rows={(point) => categories.map((category) => ({
              color: categoryColors[category],
              label: categoryLabels[category],
              value: `${quantityLabel(Number(point[category] ?? 0))}×`,
            }))}
          />
        </LineChart>
      </div>

      {checkpoints.length === 1 && <p className="momentum-note">History starts here. New exchange observations will extend this chart without replacing this checkpoint.</p>}

      <div className="momentum-table responsive-table">
        <table>
          <caption>Latest stored subscription checkpoints</caption>
          <thead><tr><th>Exchange time</th>{categories.map((category) => <th key={category}>{categoryLabels[category]}</th>)}</tr></thead>
          <tbody>{tableCheckpoints.map((checkpoint) => <tr key={checkpoint.capturedAt}>
            <td data-label="Exchange time"><time dateTime={checkpoint.capturedAt}>{checkpointLabel(checkpoint.capturedAt)}</time></td>
            {categories.map((category) => <td data-label={categoryLabels[category]} key={category}><strong>{checkpoint.values.has(category) ? `${quantityLabel(checkpoint.values.get(category) ?? 0)}×` : "—"}</strong></td>)}
          </tr>)}</tbody>
        </table>
      </div>
    </section>
  );
}
