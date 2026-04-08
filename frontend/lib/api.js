const API = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

function getToken() {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("jt_token");
}

async function request(path, { method = "GET", body, params } = {}) {
  const url = new URL(`${API}${path}`);
  if (params) {
    Object.entries(params).forEach(([k, v]) => {
      if (v !== null && v !== undefined && v !== "") {
        url.searchParams.set(k, v);
      }
    });
  }

  const headers = { "Content-Type": "application/json" };
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(url.toString(), {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });

  if (!res.ok) {
    if (res.status === 401 && token) {
      clearToken();
      if (typeof window !== "undefined") {
        window.location.href = "/login";
      }
    }
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail.detail || `HTTP ${res.status}`);
  }
  if (res.status === 204) return null;
  return res.json();
}

export function fetchJobs({ query, stage, limit = 50, offset = 0 } = {}) {
  return request("/jobs", { params: { query, stage, limit, offset } });
}

export function fetchJob(jobId) {
  return request(`/jobs/${jobId}`);
}

export function fetchTimeline(jobId) {
  return request(`/jobs/${jobId}/timeline`);
}

export function updateJob(jobId, fields) {
  return request(`/jobs/${jobId}`, { method: "PATCH", body: fields });
}

export function changeStage(jobId, newStage, reason) {
  return request(`/jobs/${jobId}/stage`, {
    method: "POST",
    body: { new_stage: newStage, reason },
  });
}

export function deleteJob(jobId) {
  return request(`/jobs/${jobId}`, { method: "DELETE" });
}

export function mergeJobs(targetJobId, sourceJobIds) {
  return request("/jobs/merge", {
    method: "POST",
    body: { target_job_id: targetJobId, source_job_ids: sourceJobIds },
  });
}

export function fetchAlerts({ limit = 50, offset = 0 } = {}) {
  return request("/alerts", { params: { limit, offset } });
}

export function deleteAlert(alertId) {
  return request(`/alerts/${alertId}`, { method: "DELETE" });
}

export function fetchRecruiters({ limit = 50, offset = 0, query } = {}) {
  const params = { limit, offset };
  if (query != null && String(query).trim() !== "") params.query = String(query).trim();
  return request("/recruiters", { params });
}

export function fetchRecruiter(recruiterId) {
  return request(`/recruiters/${recruiterId}`);
}

export function deleteRecruiter(recruiterId) {
  return request(`/recruiters/${recruiterId}`, { method: "DELETE" });
}

export function mergeRecruiters(targetContactId, sourceContactIds) {
  return request("/recruiters/merge", {
    method: "POST",
    body: {
      target_contact_id: targetContactId,
      source_contact_ids: sourceContactIds,
    },
  });
}

export function fetchMergeSuggestions({ status = "pending", limit = 50, offset = 0 } = {}) {
  return request("/merge-suggestions", { params: { status, limit, offset } });
}

export function applyMergeSuggestion(suggestionId) {
  return request(`/merge-suggestions/${suggestionId}/apply`, { method: "POST" });
}

export function login(email, password) {
  return request("/auth/login", { method: "POST", body: { email, password } });
}

export function register(tenantName, email, password) {
  return request("/auth/register", {
    method: "POST",
    body: { tenant_name: tenantName, email, password },
  });
}

export function requestForgotPassword(email) {
  return request("/auth/forgot-password", {
    method: "POST",
    body: { email },
  });
}

export function resetPassword(token, newPassword) {
  return request("/auth/reset-password", {
    method: "POST",
    body: { token, new_password: newPassword },
  });
}

export function fetchMe() {
  return request("/auth/me");
}

/** Get JWT exp (seconds since epoch) from token, or null if invalid. */
export function getTokenExp(token) {
  if (!token || typeof token !== "string") return null;
  try {
    const payload = JSON.parse(atob(token.split(".")[1]));
    return typeof payload.exp === "number" ? payload.exp : null;
  } catch {
    return null;
  }
}

/** Refresh access token using current token. Call before expiry to avoid mid-session logout. */
export async function refreshAccessToken() {
  const token = getToken();
  if (!token) return null;
  const res = await fetch(`${API}/auth/refresh`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
  });
  if (!res.ok) return null;
  const data = await res.json();
  if (data.access_token) setToken(data.access_token);
  return data.access_token || null;
}

export function setToken(token) {
  if (typeof window !== "undefined") localStorage.setItem("jt_token", token);
}

export function clearToken() {
  if (typeof window !== "undefined") localStorage.removeItem("jt_token");
}

export function startGmailOAuth() {
  return request("/email-accounts/gmail/start-oauth", { method: "POST" });
}

export function listEmailAccounts() {
  return request("/email-accounts");
}

/** Returns { accounts: [{ id, ok, detail }] } for active Gmail connections. */
export function checkGmailTokenHealth() {
  return request("/email-accounts/gmail-token-health");
}

export function disconnectEmailAccount(accountId) {
  return request(`/email-accounts/${accountId}/disconnect`, { method: "POST" });
}

export function checkLlmKey(provider = "openai") {
  return request("/llm-keys", { params: { provider } });
}

export function setLlmKey(apiKey, provider = "openai") {
  return request("/llm-keys", {
    method: "PUT",
    body: { api_key: apiKey, provider },
  });
}

export function deleteAccountMessages(accountId) {
  return request(`/email-accounts/${accountId}/messages`, { method: "DELETE" });
}

export function triggerSync(accountId, lookbackDays = null) {
  return request(`/email-accounts/${accountId}/sync`, {
    method: "POST",
    params: lookbackDays ? { lookback_days: lookbackDays } : undefined,
  });
}

export function fetchAnalyticsSummary() {
  return request("/analytics/summary");
}

export function fetchAnalyticsFunnel() {
  return request("/analytics/funnel");
}

export function fetchAnalyticsTimeseries(window = "30d") {
  return request("/analytics/timeseries", { params: { window } });
}

export function fetchAnalyticsFunnelFlow() {
  return request("/analytics/funnel-flow");
}

// ----- AI Reply Drafts (human-in-the-loop) -----

export function createDraftReply(jobId, { sourceMessageId, userInstruction } = {}) {
  const body = {
    source_message_id: sourceMessageId || null,
    user_instruction: userInstruction || null,
  };
  return request(`/jobs/${jobId}/draft-reply`, {
    method: "POST",
    body,
  });
}

export function getDraft(draftId) {
  return request(`/drafts/${draftId}`);
}

/** Get unsent draft for a job, if any. Returns null if 404 (no draft). */
export async function getDraftForJob(jobId) {
  try {
    return await request(`/jobs/${jobId}/draft`);
  } catch (err) {
    if (err.status === 404 || err.message?.includes("404")) return null;
    throw err;
  }
}

export function updateDraft(draftId, { subject, body_text }) {
  return request(`/drafts/${draftId}`, {
    method: "PATCH",
    body: { subject: subject ?? undefined, body_text: body_text ?? undefined },
  });
}

export function getDraftRecipients(draftId) {
  return request(`/drafts/${draftId}/recipients`);
}

/** Default reply-all To/CC for a job (optional source message). Use when opening Reply before a draft exists. */
export function getJobReplyRecipients(jobId, sourceMessageId = null) {
  const params = sourceMessageId ? { source_message_id: sourceMessageId } : {};
  return request(`/jobs/${jobId}/reply-recipients`, { params });
}

/** Create a draft without AI (user subject/body). Use when sending without Suggest Reply. */
export function createComposeDraft(jobId, { sourceMessageId, subject, body_text } = {}) {
  return request(`/jobs/${jobId}/compose-draft`, {
    method: "POST",
    body: {
      source_message_id: sourceMessageId || undefined,
      subject: subject ?? undefined,
      body_text: body_text ?? undefined,
    },
  });
}

export function sendDraft(draftId, { to_addrs, cc_addrs } = {}) {
  const body =
    to_addrs != null
      ? { to_addrs: to_addrs || [], cc_addrs: cc_addrs || [] }
      : undefined;
  return request(`/drafts/${draftId}/send`, {
    method: "POST",
    body,
  });
}

/** Generate follow-up email suggestion for a stalled job; creates a draft and returns it. */
export function generateFollowUpSuggestion(jobId) {
  return request(`/jobs/${jobId}/follow-up-suggestion`, { method: "POST" });
}

// ----- Resumes -----

export function uploadResume(file) {
  const API = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";
  const token = getToken();
  const form = new FormData();
  form.append("file", file);
  const headers = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;
  return fetch(`${API}/resumes/upload`, {
    method: "POST",
    headers,
    body: form,
  }).then(async (res) => {
    if (!res.ok) {
      const detail = await res.json().catch(() => ({}));
      const err = new Error(detail.detail || `HTTP ${res.status}`);
      if (res.status === 401 && token) {
        clearToken();
        if (typeof window !== "undefined") window.location.href = "/login";
      }
      throw err;
    }
    return res.json();
  });
}

export function fetchResumes() {
  return request("/resumes");
}

export function fetchResume(resumeId) {
  return request(`/resumes/${resumeId}`);
}

export function updateResume(resumeId, { name, parsed_json }) {
  return request(`/resumes/${resumeId}`, {
    method: "PATCH",
    body: { name: name ?? undefined, parsed_json: parsed_json ?? undefined },
  });
}

export function deleteResume(resumeId) {
  return request(`/resumes/${resumeId}`, { method: "DELETE" });
}

export function reviewResume(resumeId) {
  return request(`/resumes/${resumeId}/review`, { method: "POST" });
}

/** Download resume as PDF; returns blob and triggers browser download. */
export async function exportResumePdf(resumeId) {
  const API = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";
  const token = getToken();
  const headers = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const res = await fetch(`${API}/resumes/${resumeId}/export`, { headers });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail.detail || `HTTP ${res.status}`);
  }
  const blob = await res.blob();
  const filename =
    res.headers.get("Content-Disposition")?.match(/filename="?([^";]+)"?/)?.[1] ||
    "resume.pdf";
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
