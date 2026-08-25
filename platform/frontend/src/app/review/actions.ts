"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { approveRun, reviewRun, ReviewResolution } from "@/lib/review-api";

function required(formData: FormData, key: string) {
  const value = String(formData.get(key) ?? "").trim();
  if (!value) throw new Error(`${key} is required`);
  return value;
}

export async function reviewAndApprove(formData: FormData) {
  const runId = Number(required(formData, "run_id"));
  const reviewer = required(formData, "reviewer");
  const issueCount = Number(required(formData, "issue_count"));
  const resolutions: ReviewResolution[] = Array.from({ length: issueCount }, (_, index) => ({
    issue_code: required(formData, `issue_code_${index}`),
    disposition: required(formData, `disposition_${index}`),
    note: required(formData, `note_${index}`),
  }));
  await reviewRun(runId, reviewer, resolutions);
  await approveRun(runId, reviewer);
  revalidatePath("/review");
  redirect(`/review?approved=${runId}`);
}

export async function approveReviewed(formData: FormData) {
  const runId = Number(required(formData, "run_id"));
  const approver = required(formData, "approver");
  await approveRun(runId, approver);
  revalidatePath("/review");
  redirect(`/review?approved=${runId}`);
}
