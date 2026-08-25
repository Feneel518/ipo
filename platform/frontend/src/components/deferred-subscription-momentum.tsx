"use client";

import dynamic from "next/dynamic";
import { useEffect, useRef, useState } from "react";
import type { Subscription, SubscriptionMomentumRow } from "@/lib/types";

const SubscriptionMomentum = dynamic(
  () => import("@/components/subscription-momentum").then((module) => module.SubscriptionMomentum),
  { ssr: false },
);

type DeferredSubscriptionMomentumProps = {
  slug: string;
  exchange?: Subscription["exchange"];
  scope?: Subscription["bid_data_scope"];
};

export function DeferredSubscriptionMomentum({ slug, exchange, scope }: DeferredSubscriptionMomentumProps) {
  const boundaryRef = useRef<HTMLDivElement>(null);
  const [shouldLoad, setShouldLoad] = useState(false);
  const [subscriptions, setSubscriptions] = useState<SubscriptionMomentumRow[] | null>(null);

  useEffect(() => {
    const boundary = boundaryRef.current;
    if (!boundary || shouldLoad) return;

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (!entry?.isIntersecting) return;
        setShouldLoad(true);
        observer.disconnect();
      },
      { rootMargin: "500px 0px" },
    );
    observer.observe(boundary);
    return () => observer.disconnect();
  }, [shouldLoad]);

  useEffect(() => {
    if (!shouldLoad || subscriptions) return;
    const controller = new AbortController();
    const query = new URLSearchParams({ ipo: slug });
    if (exchange) query.set("exchange", exchange);
    if (scope) query.set("scope", scope);

    fetch(`/api/subscription-momentum?${query}`, { signal: controller.signal })
      .then((response) => response.ok ? response.json() as Promise<SubscriptionMomentumRow[]> : [])
      .then(setSubscriptions)
      .catch((error: unknown) => {
        if (!(error instanceof DOMException && error.name === "AbortError")) setSubscriptions([]);
      });
    return () => controller.abort();
  }, [exchange, scope, shouldLoad, slug, subscriptions]);

  return (
    <div ref={boundaryRef} className={`deferred-chart${subscriptions ? " is-loaded" : ""}`}>
      {subscriptions
        ? <SubscriptionMomentum subscriptions={subscriptions} exchange={exchange} scope={scope} />
        : <div className="demand-chart-placeholder" aria-hidden="true" />}
    </div>
  );
}
