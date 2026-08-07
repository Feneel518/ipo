/**
 * Single source of truth for how often each data type is expected to
 * refresh. `next.config.ts` reads these to define named `cacheLife`
 * profiles for `web/src/lib/ipo.ts`; UI freshness badges
 * (`components/freshness.tsx`) use the same seconds to judge when
 * displayed data has gone stale, so the two never drift apart.
 *
 * No side effects, importable from both `next.config.ts` (plain Node) and
 * app code.
 */
export const REVALIDATE_SECONDS = {
  /** IPO lists and detail shells: metadata that changes a few times a day at most. */
  ipoShell: 300,
  /** Subscription numbers on open IPOs, snapshotted by the worker every 4 minutes. */
  subscriptionFragment: 90,
  /**
   * Listing/current-price performance, refreshed once daily by the EOD price
   * job. Mirrors Next's built-in `hours` cacheLife preset (1h revalidate).
   */
  listingPerformance: 60 * 60,
} as const;
