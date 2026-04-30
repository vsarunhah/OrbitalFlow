/**
 * Shared stage constants and utilities for the Jobs UI.
 *
 * `STAGE_TONE` maps each stage to a compact palette entry used by the dot,
 * pill, and popover. Keep tones saturated enough to scan quickly on dark bg
 * but not so loud they shout — matching a Linear/Superhuman aesthetic.
 */

export const STAGES = [
  "SOURCED",
  "APPLIED",
  "SCREEN",
  "INTERVIEW",
  "TAKEHOME",
  "FINAL",
  "OFFER",
  "REJECTED",
  "WITHDRAWN",
];

export const STAGE_TONE = {
  SOURCED: { color: "#94a3b8", label: "Sourced" },
  APPLIED: { color: "#60a5fa", label: "Applied" },
  SCREEN: { color: "#a78bfa", label: "Screen" },
  INTERVIEW: { color: "#f59e0b", label: "Interview" },
  TAKEHOME: { color: "#ec4899", label: "Takehome" },
  FINAL: { color: "#2dd4bf", label: "Final" },
  OFFER: { color: "#22c55e", label: "Offer" },
  REJECTED: { color: "#ef4444", label: "Rejected" },
  WITHDRAWN: { color: "#6b7280", label: "Withdrawn" },
};

export function toneFor(stage) {
  return STAGE_TONE[stage] || { color: "#6b7280", label: stage || "Unknown" };
}

export function normalizeStageFilter(arr) {
  const allowed = new Set(STAGES);
  const picked = new Set((Array.isArray(arr) ? arr : []).filter((s) => allowed.has(s)));
  return STAGES.filter((s) => picked.has(s));
}

export function parseStagesFromQuery(stageStr) {
  if (!stageStr || typeof stageStr !== "string") return [];
  return normalizeStageFilter(
    stageStr
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean)
  );
}

export function firstQueryValue(v) {
  if (typeof v === "string") return v;
  if (Array.isArray(v) && typeof v[0] === "string") return v[0];
  return "";
}

export function buildJobsListQuery({ q, stage, view, unreadOnly }) {
  const query = {};
  const trimmed = (q || "").trim();
  if (trimmed) query.q = trimmed;
  const stages = normalizeStageFilter(stage);
  if (stages.length) query.stage = stages.join(",");
  if (view && view !== "all") query.view = view;
  if (unreadOnly) query.unread = "1";
  return query;
}
