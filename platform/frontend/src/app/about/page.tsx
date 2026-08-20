import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = { title: "About" };
export default function AboutPage() {
  return <article className="prose-page"><p className="overline">About IPO Dekho</p><h1>A calmer view of India&apos;s IPO market.</h1><p className="lede">IPO information is often scattered between exchange pages, documents and dense demand tables. IPO Dekho brings the official facts into one legible, source-linked record.</p><section><span>Why</span><div><h2>Clarity over calls</h2><p>There are no ratings, tips or manufactured urgency here. The product is designed to help readers find dates, terms, demand and listing outcomes, then return to the official filing before making a decision.</p></div></section><section><span>Data</span><div><h2>NSE and BSE first</h2><p>Every issue links back to the exchange record. See the <Link href="/methodology">methodology</Link> for collection and reconciliation details.</p></div></section><section><span>Corrections</span><div><h2>Found a discrepancy?</h2><p>Contact the operator listed in the deployment configuration with the IPO name, exchange and official source URL. Corrections should remain evidence-based and auditable.</p></div></section></article>;
}
