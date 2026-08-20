import Link from "next/link";

export function SiteFooter() {
  return (
    <footer className="site-footer">
      <div><strong>IPO Dekho</strong><p>Official-source IPO information, organized for clarity.</p></div>
      <div className="footer-links"><Link href="/methodology">Data methodology</Link><Link href="/about">About & contact</Link></div>
      <p className="disclaimer">Information only. IPO Dekho does not provide investment advice or recommend securities.</p>
    </footer>
  );
}
