import { CalendarEvent, IpoDetailData, IpoPageData, Summary } from "./types";

const apiBase = process.env.API_BASE_URL ?? "http://localhost:8080";

async function api<T>(path: string): Promise<T> {
  const response = await fetch(`${apiBase}${path}`, { next: { revalidate: 300 } });
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

export async function getSummary(): Promise<Summary> {
  try {
    return await api<Summary>("/api/v1/meta/summary");
  } catch {
    return { open: 0, upcoming: 0, listed: 0, mainboard: 0, sme: 0, last_updated_at: null };
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
