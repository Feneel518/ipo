"use client";

import { useMemo } from "react";
import { defaultScatterColors } from "@/components/charts/chart-context";
import { Grid } from "@/components/charts/grid";
import { Line, LineChart } from "@/components/charts/line-chart";
import { ReferenceArea } from "@/components/charts/reference-area";
import { ChartTooltip } from "@/components/charts/tooltip";
import { XAxis } from "@/components/charts/x-axis";
import type { Subscription, SubscriptionMomentumRow } from "@/lib/types";

const chartCategories = ["TOTAL", "RETAIL", "NII", "QIB"] as const;
const categoryLabels: Record<string, string> = {
  TOTAL: "Total",
  RETAIL: "Retail",
  NII: "NII",
  QIB: "QIB",
};
const categoryColors: Record<string, string> = {
  TOTAL: defaultScatterColors[0],
  RETAIL: defaultScatterColors[1],
  NII: defaultScatterColors[2],
  QIB: defaultScatterColors[3],
};

const subscriptionDateFormatter = new Intl.DateTimeFormat("en-IN", {
  day: "numeric",
  month: "short",
  timeZone: "Asia/Kolkata",
});
const subscriptionTimestampFormatter = new Intl.DateTimeFormat("en-IN", {
  dateStyle: "medium",
  timeStyle: "short",
  timeZone: "Asia/Kolkata",
});

const MAX_VISIBLE_CHECKPOINT_GAP_MS = 10 * 60 * 1000;

function compressCheckpointTimes(checkpoints: Array<{ capturedAt: string }>) {
  let previousActualTime: number | null = null;
  let compressedTime = Date.UTC(2000, 0, 1);

  return checkpoints.map((checkpoint) => {
    const actualTime = Date.parse(checkpoint.capturedAt);
    if (previousActualTime != null) {
      compressedTime += Math.min(Math.max(actualTime - previousActualTime, 1), MAX_VISIBLE_CHECKPOINT_GAP_MS);
    }
    previousActualTime = actualTime;
    return compressedTime;
  });
}

function quantityLabel(value: number) {
  return new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2 }).format(value);
}

interface SubscriptionMomentumProps {
  subscriptions: SubscriptionMomentumRow[];
  exchange?: Subscription["exchange"];
  scope?: Subscription["bid_data_scope"];
}

export function SubscriptionMomentum({ subscriptions, exchange, scope }: SubscriptionMomentumProps) {
  const { checkpoints, categories, fullData } = useMemo(() => {
    const revisions = subscriptions
      .filter((item) => item.exchange === exchange
        && item.bid_data_scope === scope
        && item.calculated_subscription != null
        && Number.isFinite(Number(item.calculated_subscription)))
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

    const nextCheckpoints = [...checkpointMap.entries()]
      .sort(([left], [right]) => Date.parse(left) - Date.parse(right))
      .map(([capturedAt, values]) => ({ capturedAt, values }));
    const nextCategories = chartCategories.filter((category) => nextCheckpoints.some((checkpoint) => checkpoint.values.has(category)));
    const carriedValues = new Map<string, number>();
    const compressedTimes = compressCheckpointTimes(nextCheckpoints);
    const nextData = nextCheckpoints.map((checkpoint, index) => {
      const capturedAt = new Date(checkpoint.capturedAt);
      for (const category of nextCategories) {
        const value = checkpoint.values.get(category);
        if (value != null) carriedValues.set(category, value);
      }

      return {
        date: new Date(compressedTimes[index] ?? Date.UTC(2000, 0, 1)),
        capturedAtLabel: subscriptionDateFormatter.format(capturedAt),
        capturedAtTooltip: subscriptionTimestampFormatter.format(capturedAt),
        ...Object.fromEntries(nextCategories.map((category) => [category, carriedValues.get(category) ?? 0])),
      };
    });

    return { checkpoints: nextCheckpoints, categories: nextCategories, fullData: nextData };
  }, [exchange, scope, subscriptions]);
  if (!checkpoints.length || !categories.length) return null;

  return (
    <figure className="demand-plot" aria-labelledby="subscription-curve-title">
      <header className="demand-plot-heading">
        <div><span id="subscription-curve-title">Subscription curve</span><small>{checkpoints.length} exchange {checkpoints.length === 1 ? "update" : "updates"} on record</small></div>
        <div className="demand-line-key" aria-label="Chart legend">{categories.map((category) => <span key={category} style={{ color: categoryColors[category] }}><i />{categoryLabels[category]}</span>)}</div>
      </header>
      <div className="demand-chart" aria-label={`${categories.map((category) => categoryLabels[category]).join(", ")} subscription multiples across ${checkpoints.length} stored exchange checkpoints`}>
        <span className="demand-axis-label" aria-hidden="true">Subscription (×)</span>
        <span className="demand-threshold-label" aria-hidden="true">Below 1×</span>
        <LineChart aspectRatio="16 / 5" data={fullData} dateLabelKey="capturedAtLabel" margin={{ top: 28, right: 24, bottom: 42, left: 24 }} xDataKey="date" yDomainTween>
          <Grid horizontal />
          <ReferenceArea axisLabelColor="var(--orange)" fadeEdges fadeEdgesLength={10} fill="rgba(140,47,29,.07)" fillOpacity={1} pattern="none" patternColor="var(--rule)" stroke="rgba(140,47,29,.55)" strokeDasharray="4,4" strokeStyle="dashed" y1={0} y2={1} yAxisId="left" />
          {categories.map((category) => <Line dataKey={category} key={category} stroke={categoryColors[category]} strokeWidth={category === "TOTAL" ? 3 : 2} />)}
          <XAxis numTicks={Math.min(5, checkpoints.length)} tickMode="data" />
          <ChartTooltip backgroundColor="var(--field)" className="gazette-chart-tooltip" indicatorColor="var(--orange)" indicatorFadeEdges="none" panelStyle={{ border: "1px solid var(--ink)", borderRadius: 0, boxShadow: "4px 4px 0 var(--paper-deep)", color: "var(--ink)", backdropFilter: "none" }} rows={(point) => categories.map((category) => ({ color: categoryColors[category], label: categoryLabels[category], value: `${quantityLabel(Number(point[category] ?? 0))}×` }))} showDatePill={false} title={(point) => String(point.capturedAtTooltip ?? "Exchange checkpoint")} />
        </LineChart>
      </div>
      {checkpoints.length === 1 && <p className="demand-first-update">The first checkpoint is in. This curve will grow with each exchange update.</p>}
      <figcaption>{exchange} · {scope === "ALL_EXCHANGES" ? "All exchanges" : "Reported book"} · Intraday checkpoints are spaced for readability.</figcaption>
    </figure>
  );
}
