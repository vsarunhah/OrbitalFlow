/**
 * Relative time formatting for activity timestamps.
 * Kept separate from React components so they're trivially unit-testable.
 */

export function formatRelativeActivity(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  const now = new Date();
  const diffMs = now - d;
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 1) return "now";
  if (diffMin < 60) return `${diffMin}m`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h`;
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const startOfD = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  const diffDays = Math.floor((startOfToday - startOfD) / 864e5);
  if (diffDays <= 0) return `${diffHr}h`;
  if (diffDays < 7) return `${diffDays}d`;
  if (diffDays < 84) return `${Math.floor(diffDays / 7)}w`;
  if (diffDays < 365) return `${Math.max(1, Math.floor(diffDays / 30))}mo`;
  return `${Math.max(1, Math.floor(diffDays / 365))}y`;
}

export function formatActivityTooltip(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleString();
}
