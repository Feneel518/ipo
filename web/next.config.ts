import type { NextConfig } from "next";

import { REVALIDATE_SECONDS } from "./src/lib/cache-profiles";

const nextConfig: NextConfig = {
  cacheComponents: true,
  cacheLife: {
    // IPO lists and detail shells (web/src/lib/ipo.ts: getLiveIpos, getIpoBySlug).
    ipoShell: {
      stale: 60,
      revalidate: REVALIDATE_SECONDS.ipoShell,
      expire: REVALIDATE_SECONDS.ipoShell * 12,
    },
    // Subscription numbers on open IPOs (getSubscriptionHistory) — kept as its
    // own short-lived fragment so it can refresh without invalidating the
    // slower-changing IPO shell around it.
    subscriptionFragment: {
      stale: 30,
      revalidate: REVALIDATE_SECONDS.subscriptionFragment,
      expire: REVALIDATE_SECONDS.subscriptionFragment * 6,
    },
    // Past-performance data (getRecentlyListedIpos) uses the built-in `hours`
    // preset directly, since it already matches REVALIDATE_SECONDS.listingPerformance.
  },
};

export default nextConfig;
