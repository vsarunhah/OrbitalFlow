/**
 * Normalize company for duplicate detection: ignore case and all whitespace.
 */
export function normalizeCompanyKey(name) {
  if (name == null || typeof name !== "string") return "";
  return name.trim().toLowerCase().replace(/\s+/g, "");
}

/**
 * @param {Array<{ id: string, company?: string | null, role?: string | null }>} jobList
 * @returns {Array<{ key: string, jobs: typeof jobList }>}
 */
export function groupJobsByNormalizedCompany(jobList) {
  const map = new Map();
  for (const job of jobList || []) {
    const key = normalizeCompanyKey(job.company);
    if (!key) continue;
    if (!map.has(key)) map.set(key, []);
    map.get(key).push(job);
  }
  return [...map.entries()]
    .filter(([, arr]) => arr.length >= 2)
    .map(([key, jobs]) => ({ key, jobs }));
}

export function displayCompanyForGroup(jobs) {
  const names = (jobs || []).map((j) => (j.company || "").trim()).filter(Boolean);
  if (!names.length) return "Unknown company";
  return names.reduce((best, cur) => (cur.length > best.length ? cur : best), names[0]);
}
