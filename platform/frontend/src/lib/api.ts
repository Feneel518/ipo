import { CalendarEvent, IpoDetailData, IpoPageData, Summary } from "./types";

const apiBase = process.env.API_BASE_URL ?? "http://localhost:8080";
const API_REVALIDATE_SECONDS = 300;

async function api<T>(path: string): Promise<T> {
  // Exchange ingestion runs on a five-minute cadence. Keep the last successful
  // response at the Next.js data layer so pages can be served from ISR/CDN
  // instead of blocking every visitor on the API and database.
  const response = await fetch(`${apiBase}${path}`, {
    next: { revalidate: API_REVALIDATE_SECONDS, tags: ["ipo-data"] },
  });
  if (!response.ok) throw new Error(`API ${path} returned ${response.status}`);
  return response.json() as Promise<T>;
}

export async function getIpos(params: URLSearchParams = new URLSearchParams()): Promise<IpoPageData> {
  try {
    return await api<IpoPageData>(`/api/v1/ipos?${params.toString()}`);
  } catch {
    return { data: [], meta: { next_cursor: null, last_updated_at: null } };
  }
}

export async function getAllIpos(params: URLSearchParams = new URLSearchParams()): Promise<IpoPageData> {
  const pageParams = new URLSearchParams(params);
  pageParams.set("limit", "50");

  const data: IpoPageData["data"] = [];
  let lastUpdatedAt: string | null = null;
  let cursor: number | null = null;

  do {
    if (cursor == null) pageParams.delete("cursor");
    else pageParams.set("cursor", String(cursor));

    const page = await getIpos(pageParams);
    data.push(...page.data);
    lastUpdatedAt = page.meta.last_updated_at ?? lastUpdatedAt;
    cursor = page.meta.next_cursor;
  } while (cursor != null);

  return { data, meta: { next_cursor: null, last_updated_at: lastUpdatedAt } };
}

export async function getSummary(): Promise<Summary> {
  try {
    const summary = await api<Partial<Summary>>("/api/v1/meta/summary");
    const count = (value: unknown) => typeof value === "number" && Number.isSafeInteger(value) && value >= 0 ? value : 0;
    return {
      open: count(summary.open),
      upcoming: count(summary.upcoming),
      listed: count(summary.listed),
      // Older API deployments do not return this field yet. `sme` is the
      // closest compatible value until the backend is restarted/upgraded.
      listed_sme: count(summary.listed_sme ?? summary.sme),
      mainboard: count(summary.mainboard),
      sme: count(summary.sme),
      last_updated_at: typeof summary.last_updated_at === "string" ? summary.last_updated_at : null,
    };
  } catch {
    return { open: 0, upcoming: 0, listed: 0, listed_sme: 0, mainboard: 0, sme: 0, last_updated_at: null };
  }
}

export async function getIpo(slug: string): Promise<IpoDetailData | null> {
  try {
    return await api<IpoDetailData>(`/api/v1/ipos/${encodeURIComponent(slug)}`);
  } catch {
    return null;
  }
}

export async function getCalendar(month: string): Promise<CalendarEvent[]> {
  try {
    return await api<CalendarEvent[]>(`/api/v1/calendar?month=${encodeURIComponent(month)}`);
  } catch {
    return [];
  }
}
