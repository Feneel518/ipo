import { NextRequest, NextResponse } from "next/server";
import { getIpo } from "@/lib/api";
import type { SubscriptionMomentumRow } from "@/lib/types";

export async function GET(request: NextRequest) {
  const slug = request.nextUrl.searchParams.get("ipo")?.trim();
  const exchange = request.nextUrl.searchParams.get("exchange");
  const scope = request.nextUrl.searchParams.get("scope");
  if (!slug || slug.length > 160) return NextResponse.json([], { status: 400 });

  const ipo = await getIpo(slug);
  if (!ipo) return NextResponse.json([], { status: 404 });

  const rows: SubscriptionMomentumRow[] = ipo.subscriptions
    .filter((row) => (!exchange || row.exchange === exchange) && (!scope || row.bid_data_scope === scope))
    .map((row) => ({
      exchange: row.exchange,
      bid_data_scope: row.bid_data_scope,
      captured_at: row.captured_at,
      observed_at: row.observed_at,
      category: row.category,
      calculated_subscription: row.calculated_subscription,
    }));

  return NextResponse.json(rows, {
    headers: { "Cache-Control": "public, max-age=60, s-maxage=300, stale-while-revalidate=86400" },
  });
}
