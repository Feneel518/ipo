import type { Metadata } from "next";
import Link from "next/link";
import { approveReviewed, reviewAndApprove } from "./actions";
import { getReviewQueue, ReviewRun } from "@/lib/review-api";

export const metadata: Metadata = { title: "RHP review desk", robots: { index: false, follow: false } };

function dateTime(value: string | null) {
  if (!value) return "Pending";
  return new Intl.DateTimeFormat("en-IN", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Asia/Kolkata",
  }).format(new Date(value));
}

function extractedSections(run: ReviewRun) {
  return Object.keys(run.raw_json ?? {}).filter((key) => key !== "extraction_meta");
}

function WarningReview({ run }: { run: ReviewRun }) {
  return (
    <form action={reviewAndApprove} className="review-form">
      <input type="hidden" name="run_id" value={run.run_id} />
      <input type="hidden" name="issue_count" value={run.validation_issues.length} />
      <div className="reviewer-line">
        <label><span>Reviewer name</span><input name="reviewer" required placeholder="Your name" autoComplete="name" /></label>
        <p>Every warning needs a disposition and audit note before publication.</p>
      </div>
      <ol className="review-issues">
        {run.validation_issues.map((issue, index) => (
          <li key={`${issue.code}-${index}`}>
            <input type="hidden" name={`issue_code_${index}`} value={issue.code} />
            <header><span>{issue.severity ?? "VERIFY"}</span><strong>{issue.code}</strong><small>{issue.field_path ?? "General"}</small></header>
            <p>{issue.message ?? "Model output requires human verification."}</p>
            <div>
              <label><span>Decision</span><select name={`disposition_${index}`} defaultValue="ACCEPTED"><option value="ACCEPTED">Accept as reported</option><option value="CORRECTED">Corrected externally</option><option value="SKIPPED">Exclude / skip</option></select></label>
              <label><span>Review note</span><input name={`note_${index}`} required placeholder="What did you verify?" /></label>
            </div>
          </li>
        ))}
      </ol>
      <button className="review-approve" type="submit">Review &amp; approve for publication</button>
    </form>
  );
}

function ReviewedApproval({ run }: { run: ReviewRun }) {
  return (
    <form action={approveReviewed} className="review-finalize">
      <input type="hidden" name="run_id" value={run.run_id} />
      <label><span>Approver name</span><input name="approver" required placeholder="Your name" autoComplete="name" /></label>
      <button className="review-approve" type="submit">Approve for publication</button>
    </form>
  );
}

export default async function ReviewPage({ searchParams }: { searchParams: Promise<{ approved?: string }> }) {
  const [{ approved }, queue] = await Promise.all([searchParams, getReviewQueue()]);
  const actionable = queue.data.filter((run) => run.status !== "FAILED");
  const failed = queue.data.filter((run) => run.status === "FAILED");
  return (
    <div className="review-desk">
      <header className="review-hero">
        <div><p className="gazette-kicker">Internal desk · RHP verification</p><h1>The approval ledger</h1><p>Resolve model warnings, inspect provenance, and release verified company analysis to the public record.</p></div>
        <aside><span>Awaiting review</span><strong>{queue.counts.READY_WITH_WARNINGS ?? 0}</strong><small>Prepared extractions</small></aside>
      </header>
      {approved && <p className="review-notice" role="status">Run #{approved} was approved and is now available for publication.</p>}
      <section className="review-totals" aria-label="Extraction status totals">
        {[['Ready', 'READY'], ['Warnings', 'READY_WITH_WARNINGS'], ['Reviewed', 'REVIEWED'], ['Approved', 'APPROVED'], ['Failed', 'FAILED']].map(([label, status]) => <div key={status}><span>{label}</span><strong>{queue.counts[status] ?? 0}</strong></div>)}
      </section>
      <div className="column-heading"><span>Action queue</span><span>{actionable.length} records</span></div>
      <section className="review-queue">
        {!actionable.length && <div className="review-empty"><strong>The desk is clear.</strong><p>No warning-bearing runs are waiting for approval.</p></div>}
        {actionable.map((run) => (
          <article className="review-card" key={run.run_id}>
            <header><div><span className={`review-status review-status-${run.status.toLowerCase()}`}>{run.status.replaceAll('_', ' ')}</span><h2>{run.company_name}</h2><p>Run #{run.run_id} · completed {dateTime(run.completed_at)}</p></div><Link href={`/ipo/${run.ipo_slug}`} target="_blank">Open public record ↗</Link></header>
            <div className="review-run-meta"><span>{run.model}</span><span>{run.prompt_version}</span><span>{run.schema_version}</span><span>{extractedSections(run).join(" · ")}</span></div>
            <details className="review-raw"><summary>Inspect extracted JSON</summary><pre>{JSON.stringify(run.raw_json, null, 2)}</pre></details>
            {run.status === "READY_WITH_WARNINGS" ? <WarningReview run={run} /> : <ReviewedApproval run={run} />}
          </article>
        ))}
      </section>
      {failed.length > 0 && <><div className="column-heading review-failed-heading"><span>Failed extractions</span><span>{failed.length} latest runs</span></div><section className="review-failures">{failed.map((run) => <article key={run.run_id}><header><strong>{run.company_name}</strong><span>{run.error_code ?? "EXTRACTION_FAILED"}</span></header><p>{run.error_message ?? "No error detail was recorded."}</p><small>Run #{run.run_id} · {dateTime(run.completed_at)}</small></article>)}</section></>}
    </div>
  );
}
