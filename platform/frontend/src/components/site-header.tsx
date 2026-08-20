import Link from "next/link";

export function SiteHeader() {
  return (
    <header className="site-header">
      <Link href="/" className="brand" aria-label="IPO Dekho home">
        <span className="brand-mark">ID</span>
        <span>IPO Dekho</span>
      </Link>
      <nav aria-label="Primary navigation">
        <Link href="/ipos">All IPOs</Link>
        <Link href="/calendar">Calendar</Link>
        <Link href="/methodology">Methodology</Link>
        <Link href="/about">About</Link>
      </nav>
    </header>
  );
}
