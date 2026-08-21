"use client";

import { curveNatural } from "@visx/curve";
import { chartCssVars, defaultScatterColors } from "@/components/charts/chart-context";
import { Grid } from "@/components/charts/grid";
import { Line, LineChart } from "@/components/charts/line-chart";
import { ReferenceArea } from "@/components/charts/reference-area";
import { ChartTooltip } from "@/components/charts/tooltip";
import { XAxis } from "@/components/charts/x-axis";
import type { Subscription } from "@/lib/types";

const chartCategories = ["TOTAL", "RETAIL", "NII", "QIB"] as const;
const dataCategoryOrder = ["TOTAL", "QIB", "NII", "BNII", "SNII", "RETAIL", "EMPLOYEE", "SHAREHOLDER"] as const;
const categoryLabels: Record<string, string> = {
  TOTAL: "Total",
  RETAIL: "Retail",
  NII: "NII",
  QIB: "QIB",
  BNII: "bNII",
  SNII: "sNII",
  EMPLOYEE: "Employee",
  SHAREHOLDER: "Shareholder",
};

const categoryColors: Record<string, string> = {
  TOTAL: defaultScatterColors[0],
  RETAIL: defaultScatterColors[1],
  NII: defaultScatterColors[2],
  QIB: defaultScatterColors[3],
};

function quantityLabel(value: number) {
  return new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2 }).format(value);
}

function volumeLabel(value?: string | null) {
  if (value == null || !Number.isFinite(Number(value))) return "—";
  return new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 }).format(Number(value));
}

function changeLabel(value: number) {
  if (Math.abs(value) < 0.005) return "No change";
  return `${value > 0 ? "+" : ""}${quantityLabel(value)}×`;
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
  const latestCheckpoint = checkpoints.at(-1);
  const previousCheckpoint = checkpoints.at(-2);
  const latestItems = new Map(
    [...latestRevision.values()]
      .filter((item) => item.captured_at === latestCheckpoint?.capturedAt)
      .map((item) => [item.category, item]),
  );
  const dataCategories = dataCategoryOrder.filter((category) => latestItems.has(category));
  const overall = latestItems.get("TOTAL");
  const overallMultiple = Number(overall?.calculated_subscription ?? 0);
  const isCovered = overallMultiple >= 1;

  return (
    <div className="demand-console" role="group" aria-label="Live subscription dashboard">
      <aside className="demand-score" aria-label="Overall subscription">
        <div className="demand-score-top"><span>Overall book</span><i>Live</i></div>
        <div className="demand-score-value"><strong>{quantityLabel(overallMultiple)}</strong><span>×</span></div>
        <p className={isCovered ? "is-covered" : undefined}>{isCovered ? "Issue fully covered" : "Building toward full cover"}</p>
        <div className="demand-score-meter" aria-label={`${quantityLabel(overallMultiple)} times subscribed`}><span style={{ width: `${Math.min(overallMultiple * 100, 100)}%` }} /></div>
        <div className="demand-score-scale"><span>0×</span><span>1× threshold</span></div>
        <dl>
          <div><dt>Confirmed bids</dt><dd>{volumeLabel(overall?.raw_exchange_bid_quantity)}</dd></div>
          <div><dt>Reserved shares</dt><dd>{volumeLabel(overall?.shares_reserved_for_category)}</dd></div>
          {overall?.applications != null && <div><dt>Applications</dt><dd>{volumeLabel(overall.applications)}</dd></div>}
        </dl>
      </aside>

      <div className="demand-plot">
        <header className="demand-plot-heading">
          <div><span>Subscription curve</span><small>{checkpoints.length} exchange {checkpoints.length === 1 ? "update" : "updates"}</small></div>
          <div className="demand-line-key" aria-label="Chart legend">{categories.map((category) => <span key={category} style={{ color: categoryColors[category] }}><i />{categoryLabels[category]}</span>)}</div>
        </header>
        <div className="demand-chart" aria-label={`${categories.map((category) => categoryLabels[category]).join(", ")} subscription multiples across ${checkpoints.length} stored exchange checkpoints`}>
          <span className="demand-axis-label" aria-hidden="true">Subscription (×)</span>
          <span className="demand-threshold-label" aria-hidden="true">Below 1×</span>
          <LineChart animationDuration={1100} animationEasing="cubic-bezier(0.5, 1.35, 0.5, 1)" aspectRatio="16 / 8" data={chartData} margin={{ top: 32, right: 28, bottom: 50, left: 28 }} xDataKey="date">
            <Grid horizontal stroke="rgba(255,253,247,.18)" strokeDasharray="3,7" />
            <ReferenceArea axisLabelColor="#e9784f" fadeEdges fadeEdgesLength={10} fill="rgba(233,120,79,.12)" fillOpacity={1} pattern="none" patternColor={chartCssVars.foregroundMuted} stroke="rgba(233,120,79,.65)" strokeDasharray="4,4" strokeStyle="dashed" y1={0} y2={1} yAxisId="left" />
            {categories.map((category) => <Line curve={curveNatural} dataKey={category} fadeEdges key={category} showHighlight={false} stroke={categoryColors[category]} strokeWidth={category === "TOTAL" ? 3.5 : 2.25} />)}
            <XAxis numTicks={Math.min(5, checkpoints.length)} tickMode="data" />
            <ChartTooltip showDots={false} indicatorColor="#fffdf7" rows={(point) => categories.map((category) => ({ color: categoryColors[category], label: categoryLabels[category], value: `${quantityLabel(Number(point[category] ?? 0))}×` }))} />
          </LineChart>
        </div>
        {checkpoints.length === 1 && <p className="demand-first-update">The first checkpoint is in. This curve will grow with each exchange update.</p>}
      </div>

      <div className="demand-tape" aria-label="Latest category subscription data">
        <div className="demand-tape-label"><span>Latest tape</span><small>{exchange} · {scope === "ALL_EXCHANGES" ? "All exchanges" : "Reported book"}</small></div>
        {dataCategories.filter((category) => category !== "TOTAL").map((category) => {
          const item = latestItems.get(category);
          const latest = latestCheckpoint?.values.get(category) ?? Number(item?.calculated_subscription ?? 0);
          const previous = previousCheckpoint?.values.get(category);
          const change = previous == null ? null : latest - previous;
          return <article className="demand-tape-item" key={category}>
            <header><span>{categoryLabels[category] ?? category}</span><small className={change != null && change > 0 ? "is-up" : undefined}>{change == null ? "Latest" : changeLabel(change)}</small></header>
            <strong>{quantityLabel(latest)}<i>×</i></strong>
            <dl><div><dt>Bids</dt><dd>{volumeLabel(item?.raw_exchange_bid_quantity)}</dd></div><div><dt>Reserved</dt><dd>{volumeLabel(item?.shares_reserved_for_category)}</dd></div>{item?.applications != null && <div><dt>Applications</dt><dd>{volumeLabel(item.applications)}</dd></div>}</dl>
          </article>;
        })}
      </div>
    </div>
  );
}
