import type { MetadataRoute } from "next";
import { getIpos } from "@/lib/api";

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const base = process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000";
  const result = await getIpos(new URLSearchParams({ limit: "50", sort: "updated" }));
  const staticPages = ["", "/ipos", "/calendar", "/methodology", "/about"].map((path) => ({ url: `${base}${path}`, lastModified: new Date() }));
  return [...staticPages, ...result.data.map((ipo) => ({ url: `${base}/ipo/${ipo.slug}`, lastModified: result.meta.last_updated_at ? new Date(result.meta.last_updated_at) : new Date() }))];
}
