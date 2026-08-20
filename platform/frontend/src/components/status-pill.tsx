import { Lifecycle } from "@/lib/types";
import { humanizeLabel } from "@/lib/format";

export function StatusPill({ status }: { status: Lifecycle }) {
  return <span className={`status status-${status.toLowerCase()}`}>{humanizeLabel(status)}</span>;
}
