import Link from "next/link";
export default function NotFound() { return <div className="empty-state not-found"><span>404</span><h1>This issue is off the board.</h1><p>It may have moved, or the exchange record has not been ingested yet.</p><Link className="button button-primary" href="/ipos">Browse IPOs</Link></div>; }
