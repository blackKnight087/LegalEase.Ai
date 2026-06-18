export const STAGE_COLORS: Record<string, string> = {
  NEW_INQUIRY: "bg-slate-100 text-slate-800",
  AI_REVIEW: "bg-indigo-100 text-indigo-800",
  CONSULTATION_SCHEDULED: "bg-blue-100 text-blue-800",
  DOCUMENTS_REQUESTED: "bg-amber-100 text-amber-800",
  DOCUMENTS_RECEIVED: "bg-amber-50 text-amber-900 border border-amber-200",
  QUALIFIED: "bg-emerald-100 text-emerald-800",
  ENGAGEMENT_LETTER_SENT: "bg-violet-100 text-violet-800",
  RETAINER_PAID: "bg-teal-100 text-teal-900",
  MATTER_CREATED: "bg-green-100 text-green-900",
  CLOSED_WON: "bg-green-200 text-green-900",
  CLOSED_LOST: "bg-red-100 text-red-800",
  AI_REVIEWED: "bg-indigo-100 text-indigo-800",
  DOCUMENTS_PENDING: "bg-amber-100 text-amber-800",
  REJECTED: "bg-red-100 text-red-800",
  CLOSED: "bg-gray-200 text-gray-700",
};

export const RISK_STYLES: Record<string, { badge: string; text: string }> = {
  high: { badge: "bg-red-50 text-red-800 border-red-200", text: "text-red-700" },
  medium: { badge: "bg-amber-50 text-amber-900 border-amber-200", text: "text-amber-800" },
  low: { badge: "bg-emerald-50 text-emerald-800 border-emerald-200", text: "text-emerald-700" },
};

export const PRIORITY_STYLES: Record<string, { border: string; badge: string; label: string }> = {
  high: {
    border: "border-l-red-500",
    badge: "bg-red-50 text-red-700 border-red-200",
    label: "High",
  },
  medium: {
    border: "border-l-amber-500",
    badge: "bg-amber-50 text-amber-800 border-amber-200",
    label: "Medium",
  },
  low: {
    border: "border-l-emerald-500",
    badge: "bg-emerald-50 text-emerald-800 border-emerald-200",
    label: "Low",
  },
};

export type KanbanMeta = {
  case_type_label?: string;
  priority?: string;
  ai_score?: number;
  score_band?: string;
  conversion_probability?: number;
  potential_value_inr?: number;
  days_since_created?: number;
  assigned_to?: string;
  follow_up_label?: string;
  doc_badges?: Array<{ label: string; status: string }>;
  recommended_action?: string;
  stage_label?: string;
  risk_score?: number;
  risk_tier?: string;
  risk_scale_10?: number;
};

export function formatInr(amount: number): string {
  const n = Math.round(amount || 0);
  if (n >= 10_000_000) return `₹${(n / 10_000_000).toFixed(1).replace(/\.0$/, "")} Cr`;
  if (n >= 100_000) return `₹${(n / 100_000).toFixed(n % 100_000 === 0 ? 0 : 1).replace(/\.0$/, "")}L`;
  return `₹${n.toLocaleString("en-IN")}`;
}

export function timeAgo(iso: string): string {
  if (!iso) return "";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const hrs = Math.floor((Date.now() - then) / 3_600_000);
  if (hrs < 1) return "Just now";
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  if (days === 1) return "1 day ago";
  if (days < 30) return `${days} days ago`;
  return new Date(iso).toLocaleDateString("en-IN", { day: "numeric", month: "short" });
}

export function resolveLeadRisk(lead: Record<string, unknown>): {
  risk100: number;
  tier: string;
  scale10: number;
} {
  const k = lead.kanban as KanbanMeta | undefined;
  if (k?.risk_score && k.risk_score > 0) {
    return {
      risk100: k.risk_score,
      tier: k.risk_tier || "medium",
      scale10: k.risk_scale_10 || Math.max(1, Math.round(k.risk_score / 10)),
    };
  }

  const analysis = getAnalysis(lead);
  const legacy = analysis.legacy;
  const params = (lead.extracted_params || {}) as Record<string, unknown>;
  const candidates = [lead.risk_score, params.risk_score, legacy?.risk_score];
  for (const raw of candidates) {
    const n = Number(raw);
    if (Number.isFinite(n) && n > 0) {
      const tier = n >= 70 ? "high" : n >= 40 ? "medium" : "low";
      return { risk100: Math.round(n), tier, scale10: Math.max(1, Math.min(10, Math.round(n / 10))) };
    }
  }

  const urgency = String(lead.urgency || legacy?.urgency || "MEDIUM").toUpperCase();
  const { total: leadScore } = resolveLeadScore(lead);
  let base = 35;
  if (urgency === "HIGH" || urgency === "URGENT" || urgency === "CRITICAL") base += 28;
  else if (urgency === "LOW") base -= 12;
  if (leadScore >= 75) base += 8;
  if (String(lead.calculated_intent || "").toLowerCase().includes("criminal")) base += 15;
  const risk100 = Math.max(10, Math.min(95, base));
  const tier = risk100 >= 70 ? "high" : risk100 >= 40 ? "medium" : "low";
  return { risk100, tier, scale10: Math.max(1, Math.min(10, Math.round(risk100 / 10))) };
}

export function resolveLeadScore(lead: Record<string, unknown>): {
  total: number;
  band: string;
  needsAnalysis: boolean;
} {
  let total = Number(lead.lead_score || 0);
  let band = String(lead.lead_score_band || "");
  const analysis = getAnalysis(lead);
  const fromAnalysis = analysis.lead_score?.total;
  if (typeof fromAnalysis === "number" && fromAnalysis > total) {
    total = fromAnalysis;
    band = analysis.lead_score?.band || band;
  }
  const needsAnalysis = total <= 0 && !String(lead.raw_intake_query || "").trim();
  return { total: Math.round(total), band, needsAnalysis };
}

export function getKanbanMeta(lead: Record<string, unknown>): KanbanMeta {
  const k = lead.kanban;
  const { total: score, band } = resolveLeadScore(lead);
  const base =
    k && typeof k === "object"
      ? { ...(k as KanbanMeta), ai_score: (k as KanbanMeta).ai_score ?? score }
      : null;
  if (base) {
    return {
      ...base,
      priority:
        score >= 75 ? "high" : score >= 50 ? "medium" : (base.priority as string) || "low",
      conversion_probability: base.conversion_probability ?? Math.min(95, score + 10),
      risk_score: base.risk_score ?? resolveLeadRisk(lead).risk100,
      risk_tier: base.risk_tier,
      risk_scale_10: base.risk_scale_10,
    };
  }
  const risk = resolveLeadRisk(lead);
  return {
    case_type_label: String(lead.case_type || lead.calculated_intent || "General"),
    priority: score >= 75 ? "high" : score >= 50 ? "medium" : "low",
    ai_score: score,
    conversion_probability: Math.min(95, Math.max(12, score + 10)),
    potential_value_inr: 25_000,
    days_since_created: 0,
    assigned_to: String(lead.assigned_lawyer_id || "Unassigned"),
    follow_up_label: "Follow up",
    doc_badges: [],
    recommended_action: score > 0 ? "Review lead" : "Run AI analysis on intake notes",
    risk_score: risk.risk100,
    risk_tier: risk.tier,
    risk_scale_10: risk.scale10,
    score_band: band,
  };
}

export function scoreBandColor(band: string): string {
  const b = (band || "").toLowerCase();
  if (b === "excellent" || b === "strong") return "text-emerald-700";
  if (b === "moderate") return "text-amber-700";
  return "text-red-700";
}

export function formatApiError(e: unknown): string {
  const msg = e instanceof Error ? e.message : "Request failed";
  if (/401|not authenticated|unauthorized/i.test(msg)) {
    return "Session expired — please log in again.";
  }
  if (/cannot reach api|connection failed|failed to fetch/i.test(msg)) {
    return "Cannot reach API — ensure the backend is running on port 8000.";
  }
  return msg;
}

export type AnalysisJson = {
  executive_summary?: string;
  classification?: {
    primary?: string;
    secondary?: string;
    subcategory?: string;
    confidence?: number;
  };
  applicable_laws?: Array<{ act?: string; sections?: string[]; confidence?: number }>;
  jurisdiction?: Record<string, string | number>;
  lead_score?: {
    total?: number;
    band?: string;
    factors?: Array<{ name: string; score: number; max: number; note?: string }>;
    explanation?: string;
  };
  case_strength?: { rating?: string; strengths?: string[]; weaknesses?: string[] };
  document_readiness?: {
    percent?: number;
    required?: Array<{ label: string; status: string }>;
  };
  evidence_readiness?: {
    percent?: number;
    types?: Array<{ type: string; present: boolean }>;
  };
  consultation_questions?: string[];
  contradictions?: Array<{ a: string; b: string; severity?: string }>;
  entities?: Array<{ type: string; label: string; role?: string }>;
  matter_preview?: Record<string, unknown>;
  legacy?: {
    risk_score?: number;
    urgency?: string;
    intent?: string;
    parameters?: Record<string, unknown>;
  };
};

export function getAnalysis(lead: Record<string, unknown>): AnalysisJson {
  const a = lead.analysis || lead.analysis_json;
  if (a && typeof a === "object") return a as AnalysisJson;
  return {};
}

export function whatsappUrl(phone: string, text: string): string {
  const digits = phone.replace(/\D/g, "");
  const num = digits.startsWith("91") ? digits : digits.length === 10 ? `91${digits}` : digits;
  return `https://wa.me/${num}?text=${encodeURIComponent(text)}`;
}
