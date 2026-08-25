import { redirect } from "next/navigation";

type SearchParams = Promise<{ ipo?: string | string[] }>;

export default async function LegacySubscriptionPage({ searchParams }: { searchParams: SearchParams }) {
  const requestedIpo = (await searchParams).ipo;
  const requestedSlug = Array.isArray(requestedIpo) ? requestedIpo[0] : requestedIpo;
  redirect(requestedSlug ? `/subscriptions?ipo=${encodeURIComponent(requestedSlug)}` : "/subscriptions");
}
