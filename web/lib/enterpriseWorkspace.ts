export type EnterpriseModule =
  | "dashboard"
  | "matters"
  | "client-portal"
  | "documents"
  | "court-orders"
  | "knowledge"
  | "agents"
  | "automation"
  | "compliance"
  | "analytics"
  | "storage";

export const ENTERPRISE_NAV: Array<{ id: EnterpriseModule; label: string; icon: string }> = [
  { id: "dashboard", label: "Dashboard", icon: "📊" },
  { id: "matters", label: "Matters", icon: "📂" },
  { id: "client-portal", label: "Client Portal", icon: "🤝" },
  { id: "documents", label: "Document Center", icon: "📁" },
  { id: "court-orders", label: "Court Orders", icon: "⚖️" },
  { id: "knowledge", label: "Knowledge Base", icon: "📚" },
  { id: "agents", label: "AI Agents", icon: "🤖" },
  { id: "automation", label: "Automation", icon: "⚡" },
  { id: "compliance", label: "Compliance", icon: "✅" },
  { id: "analytics", label: "Analytics", icon: "📈" },
  { id: "storage", label: "Storage", icon: "💾" },
];

export const ONBOARDING_STARTERS = [
  { label: "Upload your first document", module: "documents" as EnterpriseModule, icon: "📁" },
  { label: "Import your first court order", module: "court-orders" as EnterpriseModule, icon: "⚖️" },
  { label: "Invite a client", module: "client-portal" as EnterpriseModule, icon: "🤝" },
  { label: "Create a matter", module: "matters" as EnterpriseModule, icon: "📂", href: "/matters/new" },
];

export const PRACTICE_AREAS = ["Litigation", "Corporate", "Real Estate", "Arbitration"] as const;

export const FOLDER_TYPES = ["Pleadings", "Orders", "Evidence", "Correspondence", "Drafts", "General"] as const;

export const DOC_REQUEST_TYPES = [
  "Identity Proof",
  "Contracts",
  "Evidence",
  "Invoices",
  "Affidavits",
] as const;

export const CLIENT_UPLOAD_TYPES = [
  "Evidence",
  "Affidavit",
  "Identity Proof",
  "Agreement",
] as const;

export const ORDER_TYPES = [
  { id: "judgment", label: "Judgment" },
  { id: "interim_order", label: "Interim Order" },
  { id: "notice", label: "Notice" },
  { id: "summons", label: "Summons" },
  { id: "execution_order", label: "Execution Order" },
  { id: "order", label: "Order" },
] as const;

export type DashboardMetrics = {
  total_documents: number;
  total_orders: number;
  pending_reviews: number;
  upcoming_deadlines: number;
  client_requests: number;
  storage_mb: number;
  ocr_queue: number;
  ai_processing_queue: number;
  knowledge_base_size: number;
  open_matters: number;
  closed_matters: number;
  orders_today?: number;
  documents_awaiting_review?: number;
  pending_approvals?: number;
  active_clients?: number;
};

export type ActivityItem = {
  id: string;
  created_at: string;
  actor: string;
  message: string;
  icon?: string;
  category?: string;
};

export type PriorityItem = {
  urgency: "red" | "yellow" | "green";
  title: string;
  subtitle?: string;
  module?: string;
  href?: string;
  onboarding?: boolean;
};

export type AgentStatus = {
  id: string;
  name: string;
  description: string;
  schedule?: string;
  mode?: string;
  status: "idle" | "running";
};

export type NotificationItem = {
  id: string;
  type: string;
  title: string;
  body: string;
  urgency: string;
};

export type CommandCenterData = {
  metrics: DashboardMetrics;
  kpi_strip?: Record<string, number>;
  snapshot?: Record<string, number>;
  action_queues?: Record<string, Array<Record<string, unknown>>>;
  activity_feed?: ActivityItem[];
  priorities_today?: PriorityItem[];
  agents?: AgentStatus[];
  notifications?: NotificationItem[];
  is_empty?: boolean;
  analytics?: Record<string, unknown>;
  permission_roles?: Array<{ role: string; label: string; access: string }>;
};

/** Relative time for activity feed (e.g. "2 min ago"). */
export function formatRelativeTime(iso: string): string {
  if (!iso) return "";
  const then = new Date(iso).getTime();
  const now = Date.now();
  const sec = Math.max(0, Math.floor((now - then) / 1000));
  if (sec < 60) return `${sec || 1} sec ago`;
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min} min ago`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr} hour${hr === 1 ? "" : "s"} ago`;
  const day = Math.floor(hr / 24);
  return `${day} day${day === 1 ? "" : "s"} ago`;
}
