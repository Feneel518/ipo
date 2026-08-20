export function EmptyState({ title = "No IPOs found", message = "The exchange feeds have no matching records yet. Try another filter or return after the next daily update." }) {
  return <div className="empty-state" role="status"><span>00</span><h2>{title}</h2><p>{message}</p></div>;
}
