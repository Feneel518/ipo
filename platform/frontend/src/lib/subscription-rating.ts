import type { Segment } from "./types";

export type SubscriptionRatingTone = "poor" | "moderate" | "good" | "strong" | "very-strong" | "mixed";

export interface SubscriptionRating {
  label: string;
  tone: SubscriptionRatingTone;
}

const mainboardBands = [
  { minimum: 30, label: "Very strong", tone: "very-strong" },
  { minimum: 10, label: "Strong", tone: "strong" },
  { minimum: 3, label: "Good", tone: "good" },
  { minimum: 1, label: "Moderate", tone: "moderate" },
] as const;

const smeBands = [
  { minimum: 50, label: "Very strong", tone: "very-strong" },
  { minimum: 20, label: "Strong", tone: "strong" },
  { minimum: 5, label: "Good", tone: "good" },
  { minimum: 1, label: "Moderate", tone: "moderate" },
] as const;

export function getSubscriptionRating(rate: number, segment: Segment): SubscriptionRating {
  if (!Number.isFinite(rate) || rate < 1) return { label: "Poor", tone: "poor" };

  const band = (segment === "SME" ? smeBands : mainboardBands).find((item) => rate >= item.minimum);
  return band ?? { label: "Poor", tone: "poor" };
}

export function getOverallSubscriptionRating({
  rate,
  segment,
  qibRate,
  preliminary,
}: {
  rate: number;
  segment: Segment;
  qibRate?: number;
  preliminary: boolean;
}): SubscriptionRating & { summary: string } {
  const rating = getSubscriptionRating(rate, segment);

  if (!preliminary && rate >= (segment === "SME" ? 5 : 3) && Number.isFinite(qibRate) && Number(qibRate) < 1) {
    return {
      label: "Mixed demand",
      tone: "mixed",
      summary: "Overall demand is healthy, but the institutional book remains below 1×.",
    };
  }

  if (preliminary) {
    return {
      ...rating,
      label: `Preliminary · ${rating.label}`,
      summary: "Bidding is still open, so this is an early signal rather than a final rating.",
    };
  }

  const summaries: Record<SubscriptionRatingTone, string> = {
    poor: "The issue has not reached full subscription.",
    moderate: "The issue is covered, with measured demand.",
    good: "Demand is comfortably above the shares available.",
    strong: "The issue has attracted strong investor demand.",
    "very-strong": "The issue is heavily subscribed across the available book.",
    mixed: "Demand signals are mixed across investor categories.",
  };

  return { ...rating, summary: summaries[rating.tone] };
}

export function ratingScaleLabel(segment: Segment) {
  return segment === "SME"
    ? "SME scale: Poor <1× · Moderate 1–5× · Good 5–20× · Strong 20–50× · Very strong 50×+"
    : "Mainboard scale: Poor <1× · Moderate 1–3× · Good 3–10× · Strong 10–30× · Very strong 30×+";
}
