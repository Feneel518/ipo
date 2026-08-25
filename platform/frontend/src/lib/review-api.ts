import "server-only";

export type ReviewIssue = {
  code: string;
  severity?: string;
  field_path?: string;
  message?: string;
};

export type ReviewResolution = {
  issue_code: string;
  disposition: string;
  note: string;
};

export type ReviewRun = {
  run_id: number;
  job_id: number;
  document_id: number;
  ipo_id: number;
  company_name: string;
  ipo_slug: string;
  status: "READY_WITH_WARNINGS" | "REVIEWED" | "FAILED";
  model: string;
  prompt_version: string;
  schema_version: string;
  validation_issues: ReviewIssue[];
  review_resolutions: ReviewResolution[];
  raw_json: Record<string, unknown> | null;
  error_code: string | null;
  error_message: string | null;
  started_at: string;
  completed_at: string | null;
  reviewed_at: string | null;
  reviewed_by: string | null;
};

export type ReviewQueue = {
  data: ReviewRun[];
  counts: Record<string, number>;
};

const apiBase = process.env.API_BASE_URL ?? "http://localhost:8080";

function internalToken() {
  const token = process.env.INTERNAL_API_TOKEN;
  if (!token) throw new Error("INTERNAL_API_TOKEN is not configured for the review dashboard");
  return token;
}

async function internalApi<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${apiBase}${path}`, {
    ...init,
    cache: "no-store",
    headers: {
      Authorization: `Bearer ${internalToken()}`,
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null) as { detail?: string } | null;
    throw new Error(payload?.detail ?? `Review API returned ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export function getReviewQueue() {
  return internalApi<ReviewQueue>("/api/v1/internal/rhp-reviews");
}

export function reviewRun(runId: number, reviewer: string, resolutions: ReviewResolution[]) {
  return internalApi<{ run_id: number; status: string }>(
    `/api/v1/internal/rhp-reviews/${runId}/review`,
    { method: "POST", body: JSON.stringify({ reviewer, resolutions }) },
  );
}

export function approveRun(runId: number, approver: string) {
  return internalApi<{ run_id: number; status: string }>(
    `/api/v1/internal/rhp-reviews/${runId}/approve`,
    { method: "POST", body: JSON.stringify({ approver }) },
  );
}
