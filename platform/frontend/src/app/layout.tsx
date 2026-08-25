import type { Metadata } from "next";
import { Archivo, Bodoni_Moda, EB_Garamond, Marcellus } from "next/font/google";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";
import { getSummary } from "@/lib/api";
import "./globals.css";

const siteUrl = process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000";

const bodoni = Bodoni_Moda({ variable: "--font-bodoni", subsets: ["latin"], display: "swap" });
const garamond = EB_Garamond({ variable: "--font-garamond", subsets: ["latin"], display: "swap" });
const archivo = Archivo({ variable: "--font-archivo", subsets: ["latin"], display: "swap" });
const marcellus = Marcellus({ variable: "--font-marcellus", subsets: ["latin"], weight: "400", display: "swap" });

export const metadata: Metadata = {
  metadataBase: new URL(siteUrl),
  title: { default: "IPO Milega Gazette — NSE & BSE IPO Calendar", template: "%s | IPO Milega Gazette" },
  description: "Track current, upcoming and listed NSE, BSE, NSE SME and BSE SME IPOs from official exchange sources.",
  alternates: { canonical: "/" },
  openGraph: { title: "IPO Milega Gazette", description: "India's IPO dates, price bands and subscription data in one clear view.", type: "website", url: siteUrl },
};

export default async function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  const summary = await getSummary();
  const lastRefresh = summary.last_updated_at
    ? new Intl.DateTimeFormat("en-IN", { dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Kolkata" }).format(new Date(summary.last_updated_at))
    : "awaiting first ingestion";

  return (
    <html lang="en-IN">
      <body className={`${bodoni.variable} ${garamond.variable} ${archivo.variable} ${marcellus.variable}`}>
        <a className="skip-link" href="#main">Skip to content</a>
        <div className="page-shell">
          <SiteHeader lastRefresh={lastRefresh} />
          <main id="main">{children}</main>
          <SiteFooter />
        </div>
      </body>
    </html>
  );
}
