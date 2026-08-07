import "server-only";

import { cacheLife, cacheTag } from "next/cache";

import type { Ipo, ListingPerformance } from "@/generated/prisma/client";
import { prisma } from "@/lib/prisma";
import { ipoSlug, symbolFromSlug } from "@/lib/slug";

const LIVE_STATUSES = ["upcoming", "open"] as const;

// Dates are normalized to strings on the way out so every caller gets the
// same shape regardless of whether a value came from a fresh query or a
// cached one, and so it round-trips cleanly through JSON if ever sent to a
// client component as a prop.
function toDateOnly(value: Date | null): string | null {
  return value ? value.toISOString().slice(0, 10) : null;
}

export type IpoSummary = {
  id: string;
  slug: string;
  name: string;
  symbol: string;
  exchange: string;
  board: string;
  status: string;
  priceBandLow: number | null;
  priceBandHigh: number | null;
  lotSize: number | null;
  issueSize: number | null;
  openDate: string | null;
  closeDate: string | null;
  listingDate: string | null;
  /** When this row last changed, for "Updated X ago" freshness badges. */
  updatedAt: string;
};

export type ListingPerformanceSummary = {
  listingOpenPrice: number | null;
  listingClosePrice: number | null;
  currentPrice: number | null;
  listingPriceDate: string | null;
  currentPriceDate: string | null;
  updatedAt: string;
};

export type IpoDetail = IpoSummary & {
  exchangeSecurityCode: string | null;
  allotmentDate: string | null;
  refundDate: string | null;
  registrar: string | null;
  drhpLink: string | null;
  listingPerformance: ListingPerformanceSummary | null;
};

export type SubscriptionPoint = {
  category: string;
  capturedAt: string;
  subscriptionMultiple: number;
};

export type ListedIpoSummary = IpoSummary & {
  listingPerformance: ListingPerformanceSummary | null;
};

function toSummary(ipo: Ipo): IpoSummary {
  return {
    id: ipo.id.toString(),
    slug: ipoSlug(ipo),
    name: ipo.name,
    symbol: ipo.symbol,
    exchange: ipo.exchange,
    board: ipo.board,
    status: ipo.status,
    priceBandLow: ipo.priceBandLow?.toNumber() ?? null,
    priceBandHigh: ipo.priceBandHigh?.toNumber() ?? null,
    lotSize: ipo.lotSize,
    issueSize: ipo.issueSize?.toNumber() ?? null,
    openDate: toDateOnly(ipo.openDate),
    closeDate: toDateOnly(ipo.closeDate),
    listingDate: toDateOnly(ipo.listingDate),
    updatedAt: ipo.updatedAt.toISOString(),
  };
}

function toListingPerformanceSummary(
  listingPerformance: ListingPerformance | null
): ListingPerformanceSummary | null {
  return (
    listingPerformance && {
      listingOpenPrice: listingPerformance.listingOpenPrice?.toNumber() ?? null,
      listingClosePrice: listingPerformance.listingClosePrice?.toNumber() ?? null,
      currentPrice: listingPerformance.currentPrice?.toNumber() ?? null,
      listingPriceDate: toDateOnly(listingPerformance.listingPriceDate),
      currentPriceDate: toDateOnly(listingPerformance.currentPriceDate),
      updatedAt: listingPerformance.updatedAt.toISOString(),
    }
  );
}

function toDetail(
  ipo: Ipo & { listingPerformance: ListingPerformance | null }
): IpoDetail {
  return {
    ...toSummary(ipo),
    exchangeSecurityCode: ipo.exchangeSecurityCode,
    allotmentDate: toDateOnly(ipo.allotmentDate),
    refundDate: toDateOnly(ipo.refundDate),
    registrar: ipo.registrar,
    drhpLink: ipo.drhpLink,
    listingPerformance: toListingPerformanceSummary(ipo.listingPerformance),
  };
}

/** Upcoming and open IPOs, soonest-closing first. Revalidates every ~5 minutes. */
export async function getLiveIpos(): Promise<IpoSummary[]> {
  "use cache";
  cacheLife("ipoShell");
  cacheTag("ipos");

  const ipos = await prisma.ipo.findMany({
    where: { status: { in: [...LIVE_STATUSES] } },
    orderBy: [{ status: "asc" }, { openDate: "asc" }],
  });
  return ipos.map(toSummary);
}

/**
 * Looks up an IPO by its derived slug. The trailing slug segment narrows the
 * query to a symbol match (indexed via the ipos_symbol_exchange_key
 * constraint); the full slug is then verified in application code since the
 * same symbol can exist on more than one exchange. Revalidates every ~5
 * minutes, same as the shell it renders into.
 */
export async function getIpoBySlug(slug: string): Promise<IpoDetail | null> {
  "use cache";
  cacheLife("ipoShell");
  cacheTag("ipos");

  const candidates = await prisma.ipo.findMany({
    where: { symbol: { equals: symbolFromSlug(slug), mode: "insensitive" } },
    include: { listingPerformance: true },
  });
  const match = candidates.find((ipo) => ipoSlug(ipo) === slug);
  return match ? toDetail(match) : null;
}

/**
 * Full subscription time series for an IPO, oldest first. Cached as its own
 * fragment (~90s revalidation) separate from the IPO shell so it can refresh
 * independently while an issue is open.
 */
export async function getSubscriptionHistory(
  ipoId: string
): Promise<SubscriptionPoint[]> {
  "use cache";
  cacheLife("subscriptionFragment");
  cacheTag("subscriptions");

  const snapshots = await prisma.subscriptionSnapshot.findMany({
    where: { ipoId: BigInt(ipoId) },
    orderBy: { capturedAt: "asc" },
  });
  return snapshots.map((snapshot) => ({
    category: snapshot.category,
    capturedAt: snapshot.capturedAt.toISOString(),
    subscriptionMultiple: snapshot.subscriptionMultiple.toNumber(),
  }));
}

/**
 * Listed IPOs with their listing/current-price performance, most recently
 * listed first. Past-performance data barely changes intraday (the worker
 * only updates it once at EOD), so this revalidates on an hourly cadence.
 */
export async function getRecentlyListedIpos(): Promise<ListedIpoSummary[]> {
  "use cache";
  cacheLife("hours");
  cacheTag("listing-performance");

  const ipos = await prisma.ipo.findMany({
    where: { status: "listed" },
    orderBy: { listingDate: "desc" },
    include: { listingPerformance: true },
  });
  return ipos.map((ipo) => ({
    ...toSummary(ipo),
    listingPerformance: toListingPerformanceSummary(ipo.listingPerformance),
  }));
}
