export const AI_REVIEW_STATUS = {
  MISSING: "missing",
  QUEUED: "queued",
  READY: "ready",
  STALE: "stale",
  ERROR: "error",
};

export function createEmptyAiReview() {
  return {
    status: AI_REVIEW_STATUS.MISSING,
    model: "gpt-4.1-mini",
    prompt_version: "benchmark_review_v1",
    checked_at: null,
    verdict: null,
    summary: "",
    suggested_additions: [],
    suggested_removals: [],
    critical_spans: [],
    raw_recommendation_notes: "",
    error_message: "",
  };
}

export function ensureAiReview(record) {
  return record.ai_review ?? createEmptyAiReview();
}
