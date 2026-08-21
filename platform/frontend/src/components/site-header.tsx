import Link from "next/link";

export function SiteHeader() {
  const links = [
    ["/ipos", "All IPOs"],
    ["/calendar", "Calendar"],
    ["/methodology", "Methodology"],
    ["/about", "About"],
  ] as const;

  return (
    <header className="site-header">
      <Link href="/" className="brand" aria-label="IPO Dekho home">
        <span className="brand-mark">ID</span>
        <span>IPO Dekho</span>
      </Link>
      <nav className="desktop-nav" aria-label="Primary navigation">
        {links.map(([href, label]) => <Link href={href} key={href}>{label}</Link>)}
      </nav>
      <details className="mobile-nav">
        <summary aria-label="Open navigation menu">
          <span>Menu</span>
          <i aria-hidden="true" />
        </summary>
        <nav aria-label="Mobile navigation">
          {links.map(([href, label], index) => <Link href={href} key={href}><small>0{index + 1}</small>{label}<span aria-hidden="true">↗</span></Link>)}
        </nav>
      </details>
    </header>
  );
}
