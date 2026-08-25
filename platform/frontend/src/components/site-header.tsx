"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useSyncExternalStore } from "react";
import { getLastViewedIpo, getLastViewedIpoFallback, subscribeToLastViewedIpo } from "@/lib/last-viewed-ipo";

export function SiteHeader({ lastRefresh }: { lastRefresh: string }) {
  const pathname = usePathname();
  const currentRecord = pathname.startsWith("/ipo/") ? pathname : null;
  const lastViewedRecord = useSyncExternalStore(subscribeToLastViewedIpo, getLastViewedIpo, getLastViewedIpoFallback);
  const issueRecord = currentRecord ?? lastViewedRecord;
  const issueSlug = issueRecord.startsWith("/ipo/") ? issueRecord.slice("/ipo/".length) : null;
  const subscriptionHref = issueSlug ? `/subscriptions?ipo=${encodeURIComponent(issueSlug)}` : "/subscriptions";

  const links = [
    ["/", "Front page"],
    ["/ipos", "Directory"],
    [issueRecord, "Issue record"],
    [subscriptionHref, "Subscription"],
    ["/calendar", "Calendar"],
    ["/allotment", "Allotment"],
    ["/about", "About"],
  ] as const;
  const isActive = (href: string, label: string) => {
    if (label === "Issue record") return pathname.startsWith("/ipo/");
    if (label === "Subscription") return pathname === "/subscriptions" || pathname === "/subscription";
    return pathname === href;
  };

  return (
    <header className="site-header">
      <div className="masthead">
        <div className="masthead-edition"><span>Nº / 001 · Aug 2026</span><strong>आई॰पी॰ओ</strong><small>Daily at 7:30 PM IST</small></div>
        <Link href="/" className="brand" aria-label="IPO Milega home"><span>I P O &nbsp; M I L E G A</span><strong>GAZETTE</strong><small>Issues, price bands &amp; the exchange book</small></Link>
        <div className="masthead-source"><em>ipomilega.in</em><span>NSE · BSE · NSE SME · BSE SME</span><span>Sourced from the exchanges</span><b># 001</b></div>
      </div>
      <div className="nav-rule">
        <nav className="desktop-nav" aria-label="Primary navigation">{links.map(([href, label]) => <Link className={isActive(href, label) ? "active" : ""} href={href} key={label}>{label}</Link>)}</nav>
        <span className="refresh-note">Last refresh {lastRefresh}</span>
      </div>
      <details className="mobile-nav">
        <summary aria-label="Open navigation menu"><span>Menu</span><i aria-hidden="true" /></summary>
        <nav aria-label="Mobile navigation">{links.map(([href, label], index) => <Link href={href} key={label}><small>0{index + 1}</small>{label}<span aria-hidden="true">↗</span></Link>)}</nav>
      </details>
    </header>
  );
}
