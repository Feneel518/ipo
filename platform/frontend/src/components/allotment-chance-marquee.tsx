"use client";

import { useEffect, useRef } from "react";
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
  const trackRef = useRef<HTMLDivElement>(null);
  const groupRef = useRef<HTMLDivElement>(null);
  const estimates = estimateChances(ipo, latestSubscriptions);
  const messages = estimates.length
    ? estimates.map((estimate) => `${estimate.label} · ${formatPercent(estimate.percent)}% · 1 in ${estimate.oneIn}`)
    : ["Allotment odds · awaiting data"];
  const tickerItems = Array.from({ length: Math.max(8, messages.length * 3) }, (_, index) => messages[index % messages.length]);
  const tickerContentKey = tickerItems.join("|");
  const accessibleMessage = estimates.length
    ? `${estimates.map((estimate) => `Estimated ${estimate.label} allotment chance ${formatPercent(estimate.percent)} percent, or about 1 in ${estimate.oneIn} applications`).join(". ")}. Estimates use ${estimates.some((estimate) => estimate.basis === "applications") ? "reported applications and available lots where available" : "reported subscription multiples"}. Indicative only.`
    : "Allotment odds will appear when exchange application data is available.";

  useEffect(() => {
    const track = trackRef.current;
    const group = groupRef.current;
    if (!track || !group) return;

    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
    if (reducedMotion.matches) return;

    let groupWidth = group.getBoundingClientRect().width;
    let autoDistance = 0;
    let lastScrollY = window.scrollY;
    let direction = 1;
    let scrollBoost = 0;
    let velocity = 32;
    let previousTime = performance.now();
    let frame = 0;

    const resizeObserver = new ResizeObserver(() => {
      groupWidth = group.getBoundingClientRect().width;
    });

    const handleScroll = () => {
      const scrollDelta = window.scrollY - lastScrollY;
      if (Math.abs(scrollDelta) > 0.5) {
        direction = scrollDelta > 0 ? -1 : 1;
        scrollBoost = Math.min(88, Math.abs(scrollDelta) * 4);
      }
      lastScrollY = window.scrollY;
    };

    const animate = (time: number) => {
      const elapsed = Math.min((time - previousTime) / 1000, 0.05);
      previousTime = time;

      scrollBoost *= Math.exp(-elapsed * 5);
      const targetVelocity = direction * (32 + scrollBoost);
      velocity += (targetVelocity - velocity) * (1 - Math.exp(-elapsed * 14));
      autoDistance += velocity * elapsed;

      if (groupWidth > 0) {
        const distance = ((autoDistance % groupWidth) + groupWidth) % groupWidth;
        track.style.transform = `translate3d(${-distance}px, 0, 0)`;
      }

      frame = requestAnimationFrame(animate);
    };

    resizeObserver.observe(group);
    window.addEventListener("scroll", handleScroll, { passive: true });
    frame = requestAnimationFrame(animate);

    return () => {
      cancelAnimationFrame(frame);
      resizeObserver.disconnect();
      window.removeEventListener("scroll", handleScroll);
      track.style.removeProperty("transform");
    };
  }, [tickerContentKey]);

  return (
    <div className={`allotment-marquee ${estimates.length ? "" : "allotment-marquee-pending"}`} role="status" aria-label={accessibleMessage}>
      <div className="allotment-marquee-track" aria-hidden="true" ref={trackRef}>
        {[0, 1].map((group) => (
          <div className="allotment-marquee-group" key={group} ref={group === 0 ? groupRef : undefined}>
            {tickerItems.map((message, item) => <span key={item}>{message}</span>)}
          </div>
        ))}
      </div>
    </div>
  );
}
