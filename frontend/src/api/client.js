const API_BASE = import.meta.env.VITE_API_URL || "";
const API_TIMEOUT_MS = 15000;

async function fetchApi(path, options = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), API_TIMEOUT_MS);
  try {
    return await fetch(`${API_BASE}${path}`, { ...options, signal: controller.signal });
  } catch (err) {
    if (err.name === "AbortError") {
      throw new Error(
        "API not responding. Run: .\\stop_saas.ps1 then .\\run_saas.ps1 (API uses port 8001)"
      );
    }
    throw new Error(err.message || "Cannot reach API server");
  } finally {
    clearTimeout(timer);
  }
}

function headers(json = true) {
  const h = {};
  if (json) h["Content-Type"] = "application/json";
  const token = localStorage.getItem("legalease_token");
  if (token) h.Authorization = `Bearer ${token}`;
  return h;
}

async function parse(res) {
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const msg =
      typeof data.detail === "string"
        ? data.detail
        : Array.isArray(data.detail)
          ? data.detail[0]?.msg
          : res.statusText;
    throw new Error(msg || "Request failed");
  }
  return data;
}

export async function login(username, password) {
  const res = await fetchApi("/api/auth/login", {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({ username, password }),
  });
  return parse(res);
}

export async function register(username, password, confirm_password) {
  const res = await fetchApi("/api/auth/register", {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({ username, password, confirm_password }),
  });
  return parse(res);
}

export async function fetchMe() {
  const res = await fetchApi("/api/auth/me", { headers: headers() });
  return parse(res);
}

export async function fetchStatus() {
  const res = await fetch(`${API_BASE}/api/status`, { headers: headers(false) });
  return parse(res);
}

export async function fetchDashboardFull() {
  const res = await fetch(`${API_BASE}/api/dashboard/full`, { headers: headers() });
  return parse(res);
}

export async function fetchKbHealth() {
  const res = await fetch(`${API_BASE}/api/kb/health`, { headers: headers() });
  return parse(res);
}

export async function fetchChatHistory(limit = 12) {
  const res = await fetch(`${API_BASE}/api/chat/history?limit=${limit}`, { headers: headers() });
  return parse(res);
}

export async function sendChat({ message, mode, lang, history, attachment }) {
  const res = await fetch(`${API_BASE}/api/chat`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({ message, mode, lang, history, attachment }),
  });
  return parse(res);
}

export async function uploadOcr(file) {
  const fd = new FormData();
  fd.append("file", file);
  const res = await fetch(`${API_BASE}/api/ocr`, {
    method: "POST",
    headers: { Authorization: headers(false).Authorization },
    body: fd,
  });
  return parse(res);
}

export async function fetchDocuments() {
  const res = await fetch(`${API_BASE}/api/documents`, { headers: headers() });
  return parse(res);
}

export async function uploadDocument(file) {
  const fd = new FormData();
  fd.append("file", file);
  const res = await fetch(`${API_BASE}/api/documents/upload`, {
    method: "POST",
    headers: { Authorization: headers(false).Authorization },
    body: fd,
  });
  return parse(res);
}

export async function reindexDocuments() {
  const res = await fetch(`${API_BASE}/api/documents/index`, {
    method: "POST",
    headers: headers(),
  });
  return parse(res);
}

export async function deleteDocument(id) {
  const res = await fetch(`${API_BASE}/api/documents/${id}`, {
    method: "DELETE",
    headers: headers(),
  });
  return parse(res);
}

export async function fetchDocTimeline(id) {
  const res = await fetch(`${API_BASE}/api/documents/${id}/timeline`, { headers: headers() });
  return parse(res);
}

export async function fetchDocEntities(id) {
  const res = await fetch(`${API_BASE}/api/documents/${id}/entities`, { headers: headers() });
  return parse(res);
}

export async function ipcConvert(section) {
  const res = await fetch(`${API_BASE}/api/tools/ipc-bns/convert`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({ section }),
  });
  return parse(res);
}

export async function ipcBulk(sections) {
  const res = await fetch(`${API_BASE}/api/tools/ipc-bns/bulk`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({ sections }),
  });
  return parse(res);
}

export async function ipcCategories() {
  const res = await fetch(`${API_BASE}/api/tools/ipc-bns/categories`, { headers: headers() });
  return parse(res);
}

export async function ipcCategory(category) {
  const res = await fetch(`${API_BASE}/api/tools/ipc-bns/category/${category}`, {
    headers: headers(),
  });
  return parse(res);
}

export async function courtFeeRegions() {
  const res = await fetch(`${API_BASE}/api/tools/court-fee/regions`, { headers: headers() });
  return parse(res);
}

export async function courtFeeCalc(body) {
  const res = await fetch(`${API_BASE}/api/tools/court-fee`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify(body),
  });
  return parse(res);
}

export async function contractReview(file) {
  const fd = new FormData();
  fd.append("file", file);
  const res = await fetch(`${API_BASE}/api/tools/contract-review`, {
    method: "POST",
    headers: { Authorization: headers(false).Authorization },
    body: fd,
  });
  return parse(res);
}

export async function casePrediction(body) {
  const res = await fetch(`${API_BASE}/api/tools/case-prediction`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify(body),
  });
  return parse(res);
}

export async function checkCitations(citations) {
  const res = await fetch(`${API_BASE}/api/tools/citations`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({ citations }),
  });
  return parse(res);
}

export async function odrProposal(body) {
  const res = await fetch(`${API_BASE}/api/tools/odr`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify(body),
  });
  return parse(res);
}

export async function fetchDraftTemplates() {
  const res = await fetch(`${API_BASE}/api/drafting/templates`, { headers: headers() });
  return parse(res);
}

export async function fetchDraftFields(templateId) {
  const res = await fetch(`${API_BASE}/api/drafting/templates/${templateId}/fields`, {
    headers: headers(),
  });
  return parse(res);
}

export async function generateDraft(template, context, use_ai) {
  const res = await fetch(`${API_BASE}/api/drafting/generate`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({ template, context, use_ai }),
  });
  return parse(res);
}

export async function fetchAnalytics() {
  const res = await fetch(`${API_BASE}/api/analytics`, { headers: headers() });
  return parse(res);
}

export async function fetchSettings() {
  const res = await fetch(`${API_BASE}/api/settings`, { headers: headers() });
  return parse(res);
}

export async function upgradePlan(plan) {
  const res = await fetch(`${API_BASE}/api/settings/upgrade`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({ plan }),
  });
  return parse(res);
}

export async function fetchPayments() {
  const res = await fetch(`${API_BASE}/api/settings/payments`, { headers: headers() });
  return parse(res);
}

export async function testLlm() {
  const res = await fetch(`${API_BASE}/api/settings/llm-test`, {
    method: "POST",
    headers: headers(),
  });
  return parse(res);
}

export async function recheckLlm() {
  const res = await fetch(`${API_BASE}/api/settings/llm-recheck`, {
    method: "POST",
    headers: headers(),
  });
  return parse(res);
}

export function saveSession(token, user) {
  localStorage.setItem("legalease_token", token);
  localStorage.setItem("legalease_user", JSON.stringify(user));
}

export function clearSession() {
  localStorage.removeItem("legalease_token");
  localStorage.removeItem("legalease_user");
}

export function getStoredUser() {
  try {
    return JSON.parse(localStorage.getItem("legalease_user") || "null");
  } catch {
    return null;
  }
}

export function updateStoredUser(user) {
  localStorage.setItem("legalease_user", JSON.stringify(user));
}
