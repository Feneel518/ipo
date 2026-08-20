import type { Metadata } from "next";
import { Source_Sans_3 } from "next/font/google";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";
import "./globals.css";

const siteUrl = process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000";

const sourceSans = Source_Sans_3({
  variable: "--font-source-sans",
  subsets: ["latin"],
  display: "swap",
});

export const metadata: Metadata = {
  metadataBase: new URL(siteUrl),
  title: { default: "IPO Dekho — NSE & BSE IPO Calendar", template: "%s | IPO Dekho" },
  description: "Track current, upcoming and listed NSE, BSE, NSE SME and BSE SME IPOs from official exchange sources.",
  alternates: { canonical: "/" },
  openGraph: { title: "IPO Dekho", description: "India's IPO dates, price bands and subscription data in one clear view.", type: "website", url: siteUrl },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en-IN">
      <body className={sourceSans.variable}>
        <a className="skip-link" href="#main">Skip to content</a>
        <div className="grain" aria-hidden="true" />
        <div className="page-shell">
          <SiteHeader />
          <main id="main">{children}</main>
          <SiteFooter />
        </div>
      </body>
    </html>
  );
}
