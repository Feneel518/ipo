"use client";

import { useSyncExternalStore } from "react";

import { cn } from "@/lib/utils";

function formatAge(ageSeconds: number): string {
  if (ageSeconds < 60) return "just now";
  const minutes = Math.round(ageSeconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  return `${days}d ago`;
}

function subscribeToClock(callback: () => void): () => void {
  const id = setInterval(callback, 15_000);
  return () => clearInterval(id);
}

function getClockSnapshot(): number {
  return Date.now();
}

// No meaningful "now" on the server — returning null until the client
// mounts avoids rendering age text that mismatches the client's clock.
function getServerClockSnapshot(): number | null {
  return null;
}

export function Freshness({
  updatedAt,
  expectedIntervalSeconds,
  className,
}: {
  /** ISO timestamp the underlying data last changed — not when this page rendered. */
  updatedAt: string;
  /** Normal revalidation cadence for this data; staleness is judged relative to it. */
  expectedIntervalSeconds: number;
  className?: string;
}) {
  // The page HTML can be served from cache for minutes; "X ago" has to keep
  // ticking in the browser rather than be baked in at render time.
  const now = useSyncExternalStore(
    subscribeToClock,
    getClockSnapshot,
    getServerClockSnapshot
  );

  if (now === null) {
    // Nothing to show until mounted — "ago" text depends on the viewer's clock.
    return null;
  }

  const ageSeconds = Math.max(0, (now - new Date(updatedAt).getTime()) / 1000);
  const degraded = ageSeconds > expectedIntervalSeconds * 2;
  const age = formatAge(ageSeconds);

  return (
    <span
      className={cn(
        "text-xs",
        degraded ? "text-amber-600 dark:text-amber-500" : "text-muted-foreground",
        className
      )}
      title={new Date(updatedAt).toLocaleString()}
    >
      {degraded ? `Updated ${age} — refresh in progress` : `Updated ${age}`}
    </span>
  );
}
