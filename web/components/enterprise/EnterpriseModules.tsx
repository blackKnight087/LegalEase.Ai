"use client";

import { useCallback, useEffect, useState } from "react";
import VoiceTextarea from "@/components/ui/VoiceTextarea";
import * as api from "@/lib/api";
import {
  CLIENT_UPLOAD_TYPES,
  DOC_REQUEST_TYPES,
  FOLDER_TYPES,
  ONBOARDING_STARTERS,
  ORDER_TYPES,
  PRACTICE_AREAS,
  formatRelativeTime,
  type ActivityItem,
  type AgentStatus,
  type CommandCenterData,
  type EnterpriseModule,
  type PriorityItem,
} from "@/lib/enterpriseWorkspace";

function KpiTile({
  label,
  value,
  onClick,
  highlight,
}: {
  label: string;
  value: string | number;
  onClick?: () => void;
  highlight?: boolean;
}) {
  const Tag = onClick ? "button" : "div";
  return (
    <Tag
      type={onClick ? "button" : undefined}
      onClick={onClick}
      className={`ent-kpi-tile ${highlight ? "ent-kpi-tile--alert" : ""} ${onClick ? "cursor-pointer hover:ring-2 hover:ring-slate-300" : ""}`}
    >
      <p className="ent-kpi-tile__label m-0">{label}</p>
      <p className="ent-kpi-tile__value m-0">{value}</p>
    </Tag>
  );
}

function EmptyActivityPanel({ onNavigate }: { onNavigate: (m: EnterpriseModule) => void }) {
  return (
    <div className="ent-empty-panel">
      <p className="font-semibold text-navy m-0">No activity yet</p>
      <p className="text-sm text-slate-500 m-0 mt-1">Your firm timeline will populate automatically.</p>
      <ul className="ent-empty-actions list-none m-0 p-0 mt-4 space-y-2">
        {ONBOARDING_STARTERS.map((s) => (
          <li key={s.label}>
            {s.href ? (
              <a href={s.href} className="ent-empty-action">
                <span>{s.icon}</span> {s.label}
              </a>
            ) : (
              <button type="button" className="ent-empty-action w-full text-left" onClick={() => onNavigate(s.module)}>
                <span>{s.icon}</span> {s.label}
              </button>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

function QueueColumn({
  title,
  count,
  items,
  empty,
  isEmptyWorkspace,
}: {
  title: string;
  count: number;
  items: Array<Record<string, unknown>>;
  empty: string;
  isEmptyWorkspace?: boolean;
}) {
  return (
    <div className="ent-queue-col">
      <div className="ent-queue-col__head">
        <span className="font-semibold text-sm text-navy">{title}</span>
        <span className={`ent-queue-col__badge ${count === 0 && isEmptyWorkspace ? "ent-queue-col__badge--muted" : ""}`}>
          {count === 0 && isEmptyWorkspace ? "—" : count}
        </span>
      </div>
      <ul className="ent-queue-col__list">
        {items.length === 0 && <li className="text-xs text-slate-500 py-2 px-2">{empty}</li>}
        {items.slice(0, 5).map((it) => (
          <li key={String(it.id)} className="ent-queue-col__item">
            <p className="font-medium text-slate-900 m-0 text-sm truncate">
              {String(it.title || it.case_number || it.request_type || "Item")}
            </p>
            <p className="text-[11px] text-slate-500 m-0 mt-0.5 truncate">
              {String(it.matter_name || it.court || it.reason || it.client_email || "")}
            </p>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function DashboardModule({
  data,
  onNavigate,
}: {
  data: CommandCenterData;
  onNavigate: (m: EnterpriseModule) => void;
}) {
  const metrics = data.metrics;
  const kpi = data.kpi_strip || {};
  const snap = data.snapshot || {};
  const queues = data.action_queues || {};
  const feed = data.activity_feed || [];
  const priorities = data.priorities_today || [];
  const isEmpty = data.is_empty ?? false;
  const agents = data.agents || [];
  const roles = data.permission_roles || [];

  const urgencyIcon = (u: string) =>
    u === "red" ? "🔴" : u === "yellow" ? "🟡" : "🟢";

  const fmt = (n: number | undefined) =>
    isEmpty && (n === 0 || n === undefined) ? "—" : String(n ?? 0);

  const realFeed = feed.filter((e) => !(e as ActivityItem & { onboarding?: boolean }).onboarding);

  return (
    <div className="ent-command-center ent-command-center--dense space-y-4">
      {roles.length > 0 && (
        <div className="flex flex-wrap gap-2 items-center">
          <span className="text-[10px] font-bold uppercase text-slate-400">Roles</span>
          {roles.map((r) => (
            <span
              key={r.role}
              className="text-[11px] px-2.5 py-1 rounded-full border border-slate-200 bg-white text-slate-600"
              title={r.access}
            >
              {r.label}
            </span>
          ))}
        </div>
      )}
      <div className="ent-kpi-row">
        <KpiTile label="Documents" value={fmt(kpi.documents ?? metrics.total_documents)} onClick={() => onNavigate("documents")} />
        <KpiTile
          label="Court Orders"
          value={fmt(kpi.court_orders ?? metrics.total_orders)}
          onClick={() => onNavigate("court-orders")}
          highlight={!isEmpty && (snap.orders_today as number) > 0}
        />
        <KpiTile label="Matters" value={fmt(kpi.matters ?? metrics.open_matters)} onClick={() => onNavigate("matters")} />
        <KpiTile label="Clients" value={fmt(kpi.clients ?? metrics.active_clients)} onClick={() => onNavigate("client-portal")} />
        <KpiTile label="Storage" value={isEmpty ? "—" : `${kpi.storage_mb ?? metrics.storage_mb} MB`} onClick={() => onNavigate("storage")} />
        <KpiTile
          label="AI Tasks"
          value={fmt(kpi.ai_tasks ?? metrics.ai_processing_queue)}
          onClick={() => onNavigate("agents")}
          highlight={!isEmpty && (snap.ai_tasks_running as number) > 0}
        />
      </div>

      <div className="ent-dashboard-grid-primary">
        <section className="ent-priorities-panel legal-tools-v2__research-card">
          <h3 className="ent-panel-title m-0">Today&apos;s priorities</h3>
          <ul className="ent-priority-list">
            {priorities.map((p: PriorityItem, i) => (
              <li key={i}>
                {"href" in p && p.href ? (
                  <a href={String(p.href)} className="ent-priority-item flex gap-3 no-underline text-inherit">
                    <span className="text-lg shrink-0">{urgencyIcon(p.urgency)}</span>
                    <div>
                      <p className="font-semibold text-navy m-0 text-sm">{p.title}</p>
                      {p.subtitle && <p className="text-xs text-slate-500 m-0">{p.subtitle}</p>}
                    </div>
                  </a>
                ) : (
                  <button
                    type="button"
                    className="ent-priority-item w-full text-left"
                    onClick={() => p.module && onNavigate(p.module as EnterpriseModule)}
                  >
                    <span className="text-lg shrink-0">{urgencyIcon(p.urgency)}</span>
                    <div className="min-w-0">
                      <p className="font-semibold text-navy m-0 text-sm">{p.title}</p>
                      {p.subtitle && <p className="text-xs text-slate-500 m-0 mt-0.5">{p.subtitle}</p>}
                    </div>
                  </button>
                )}
              </li>
            ))}
          </ul>
        </section>

        <aside className="ent-activity-panel legal-tools-v2__research-card">
          <h3 className="ent-panel-title m-0">Recent activity</h3>
          {isEmpty && realFeed.length === 0 ? (
            <EmptyActivityPanel onNavigate={onNavigate} />
          ) : (
            <ul className="ent-activity-list">
              {feed.map((e: ActivityItem) => (
                <li key={e.id} className="ent-activity-item">
                  <span className="ent-activity-icon">{e.icon || "•"}</span>
                  <div className="min-w-0 flex-1">
                    <p className="ent-activity-msg m-0">
                      <strong>{e.actor}</strong> {e.message}
                    </p>
                    <p className="ent-activity-time m-0">{formatRelativeTime(e.created_at)}</p>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </aside>
      </div>

      <section className="legal-tools-v2__research-card p-4">
        <h3 className="text-sm font-semibold text-navy m-0 mb-3">AI agents</h3>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
          {agents.slice(0, 5).map((a) => (
            <button
              key={a.id}
              type="button"
              onClick={() => onNavigate("agents")}
              className={`text-left p-2 rounded-lg border text-xs ${
                a.status === "running" ? "border-emerald-300 bg-emerald-50" : "border-slate-200"
              }`}
            >
              <span className="font-semibold text-navy block truncate">{a.name}</span>
              <span className="text-slate-500">{a.status}</span>
            </button>
          ))}
        </div>
      </section>

      <div className="ent-snapshot-row">
        {[
          ["Awaiting review", snap.documents_awaiting_review, "documents"],
          ["Orders today", snap.orders_today, "court-orders"],
          ["Client requests", snap.client_requests, "client-portal"],
          ["Pending approvals", snap.pending_approvals, "client-portal"],
          ["Hearings", snap.upcoming_hearings, "automation"],
        ].map(([label, val, mod]) => (
          <button
            key={String(label)}
            type="button"
            onClick={() => onNavigate(mod as EnterpriseModule)}
            className="ent-snapshot-chip"
          >
            <span className="ent-snapshot-chip__val">{isEmpty && !val ? "—" : String(val ?? 0)}</span>
            <span className="ent-snapshot-chip__label">{String(label)}</span>
          </button>
        ))}
      </div>

      <div className="ent-queues-grid">
        <QueueColumn
          title="Pending review"
          count={(queues.documents_awaiting_review as unknown[])?.length ?? 0}
          items={(queues.documents_awaiting_review as Array<Record<string, unknown>>) || []}
          empty="Upload a document to review"
          isEmptyWorkspace={isEmpty}
        />
        <QueueColumn
          title="Client approval"
          count={(queues.awaiting_client_approval as unknown[])?.length ?? 0}
          items={(queues.awaiting_client_approval as Array<Record<string, unknown>>) || []}
          empty="Request client review on a draft"
          isEmptyWorkspace={isEmpty}
        />
        <QueueColumn
          title="Orders to comply"
          count={(queues.orders_to_comply as unknown[])?.length ?? 0}
          items={(queues.orders_to_comply as Array<Record<string, unknown>>) || []}
          empty="Import a court order"
          isEmptyWorkspace={isEmpty}
        />
        <QueueColumn
          title="Upcoming hearings"
          count={(queues.upcoming_hearings as unknown[])?.length ?? 0}
          items={(queues.upcoming_hearings as Array<Record<string, unknown>>) || []}
          empty="Add matters with hearing dates"
          isEmptyWorkspace={isEmpty}
        />
      </div>

      <div className="ent-dashboard-bottom grid md:grid-cols-3 gap-4">
        <button type="button" onClick={() => onNavigate("storage")} className="legal-tools-v2__research-card p-4 text-left hover:ring-2 hover:ring-slate-200">
          <p className="text-xs uppercase text-slate-500 m-0">Storage</p>
          <p className="text-xl font-bold text-navy m-0 mt-1">{isEmpty ? "50 GB quota" : `${metrics.storage_mb} MB used`}</p>
        </button>
        <button type="button" onClick={() => onNavigate("compliance")} className="legal-tools-v2__research-card p-4 text-left hover:ring-2 hover:ring-slate-200">
          <p className="text-xs uppercase text-slate-500 m-0">Compliance</p>
          <p className="text-xl font-bold text-navy m-0 mt-1">Audit trail</p>
        </button>
        <button type="button" onClick={() => onNavigate("knowledge")} className="legal-tools-v2__research-card p-4 text-left hover:ring-2 hover:ring-slate-200">
          <p className="text-xs uppercase text-slate-500 m-0">Knowledge base</p>
          <p className="text-xl font-bold text-navy m-0 mt-1">{fmt(metrics.knowledge_base_size)} entries</p>
        </button>
      </div>
    </div>
  );
}

const CLIENT_PORTAL_SECTIONS = [
  { id: "dashboard", label: "Client dashboard", icon: "🏠" },
  { id: "matters", label: "My matters", icon: "📂" },
  { id: "documents", label: "My documents", icon: "📄" },
  { id: "invoices", label: "Invoices", icon: "🧾" },
  { id: "messages", label: "Messages", icon: "💬" },
  { id: "tasks", label: "Tasks", icon: "✓" },
  { id: "upload", label: "Client upload", icon: "⬆️" },
  { id: "approvals", label: "Approvals", icon: "✅" },
] as const;

export function ClientPortalModule({ matters }: { matters: api.Matter[] }) {
  const [section, setSection] = useState<(typeof CLIENT_PORTAL_SECTIONS)[number]["id"]>("dashboard");
  const [data, setData] = useState<{
    portals: Array<Record<string, unknown>>;
    document_requests: Array<Record<string, unknown>>;
    approvals: Array<Record<string, unknown>>;
  } | null>(null);
  const [matterId, setMatterId] = useState("");
  const [clientEmail, setClientEmail] = useState("client@company.com");
  const [reqType, setReqType] = useState<(typeof DOC_REQUEST_TYPES)[number]>(
    DOC_REQUEST_TYPES[0]
  );
  const [uploadType, setUploadType] = useState<(typeof CLIENT_UPLOAD_TYPES)[number]>(
    CLIENT_UPLOAD_TYPES[0]
  );
  const [reviewTitle, setReviewTitle] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  const selected = matters.find((m) => m.matter_id === matterId);

  const load = useCallback(() => {
    api.fetchEnterpriseClientPortal().then(setData).catch(() => setData(null));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const createPortal = async () => {
    if (!matterId || !clientEmail.trim()) return;
    setBusy(true);
    try {
      const r = await api.createPortalAccess({
        matter_id: matterId,
        client_email: clientEmail.trim(),
      });
      setMsg(`Portal link ready: ${r.portal_path}`);
      load();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "Failed");
    } finally {
      setBusy(false);
    }
  };

  const sendDocRequest = async () => {
    if (!matterId) return;
    setBusy(true);
    try {
      await api.createEnterpriseDocRequest({
        matter_id: matterId,
        request_type: reqType,
        client_email: clientEmail,
      });
      setMsg(`Requested ${reqType} from client.`);
      load();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "Failed");
    } finally {
      setBusy(false);
    }
  };

  const sendReview = async () => {
    if (!matterId || !reviewTitle.trim()) return;
    setBusy(true);
    try {
      await api.requestEnterpriseClientReview({
        matter_id: matterId,
        title: reviewTitle,
        client_email: clientEmail,
      });
      setReviewTitle("");
      setMsg("Client review requested — appears in dashboard activity.");
      load();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "Failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-5">
      <nav className="flex flex-wrap gap-2">
        {CLIENT_PORTAL_SECTIONS.map((s) => (
          <button
            key={s.id}
            type="button"
            onClick={() => setSection(s.id)}
            className={`px-3 py-2 rounded-lg border text-sm ${
              section === s.id ? "border-navy bg-slate-900 text-white" : "hover:bg-slate-50"
            }`}
          >
            <span className="mr-1">{s.icon}</span>
            {s.label}
          </button>
        ))}
      </nav>

      {(section === "dashboard" || section === "matters") && (
      <div className="grid lg:grid-cols-3 gap-4">
        <article className="legal-tools-v2__research-card p-5 space-y-4 lg:col-span-1">
          <h2 className="font-serif text-lg font-bold text-navy m-0">Client login</h2>
          <p className="text-xs text-slate-600 m-0">Dedicated secure access per matter — magic link, no firm password.</p>
          <label className="block text-sm">
            Client email
            <input
              type="email"
              className="mt-1 w-full border rounded-lg px-3 py-2"
              value={clientEmail}
              onChange={(e) => setClientEmail(e.target.value)}
              placeholder="client@company.com"
            />
          </label>
          <label className="block text-sm">
            Matter
            <select
              className="mt-1 w-full border rounded-lg px-3 py-2"
              value={matterId}
              onChange={(e) => setMatterId(e.target.value)}
            >
              <option value="">— Select —</option>
              {matters.map((m) => (
                <option key={m.matter_id} value={m.matter_id}>
                  {m.matter_name}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            disabled={busy || !matterId}
            onClick={createPortal}
            className="w-full px-4 py-2 bg-navy text-white rounded-lg text-sm disabled:opacity-50"
          >
            Issue portal link
          </button>
        </article>

        <article className="legal-tools-v2__research-card p-5 lg:col-span-2">
          <h2 className="font-serif text-lg font-bold text-navy m-0">Matter tracking (client view)</h2>
          {selected ? (
            <div className="mt-4 grid sm:grid-cols-2 gap-3 text-sm">
              {[
                ["Matter", selected.matter_name],
                ["Status", selected.status_tier || "Active"],
                ["Case no.", selected.case_number || "—"],
                ["Next hearing", selected.next_hearing_date || "—"],
                ["Venue", selected.venue || "—"],
                ["Practice", selected.practice_area || "—"],
              ].map(([k, v]) => (
                <div key={String(k)} className="rounded-lg border border-slate-100 bg-slate-50/80 px-3 py-2">
                  <p className="text-[10px] uppercase text-slate-500 m-0">{k}</p>
                  <p className="font-semibold text-navy m-0 mt-1">{String(v)}</p>
                </div>
              ))}
              <div className="sm:col-span-2 rounded-lg border border-amber-100 bg-amber-50/80 px-3 py-2">
                <p className="text-[10px] uppercase text-amber-800 m-0">Expected action</p>
                <p className="text-sm text-amber-900 m-0 mt-1">
                  Upload requested documents or approve pending draft via portal link.
                </p>
              </div>
            </div>
          ) : (
            <p className="text-sm text-slate-500 mt-3 m-0">Select a matter to preview client dashboard fields.</p>
          )}
        </article>
      </div>
      )}

      {section === "messages" && (
        <article className="legal-tools-v2__research-card p-5 space-y-3">
          <h3 className="font-semibold m-0">Secure messaging</h3>
          <p className="text-xs text-slate-500 m-0">Matter-scoped threads visible to client on portal.</p>
          <VoiceTextarea
            value={message}
            onChange={setMessage}
            rows={4}
            placeholder="Message to client…"
            className="w-full border rounded-lg px-3 py-2 text-sm"
          />
          <button type="button" disabled className="px-4 py-2 border rounded-lg text-sm opacity-50">
            Send via portal (beta)
          </button>
        </article>
      )}

      {(section === "upload" || section === "documents") && (
      <div className="grid lg:grid-cols-2 gap-4">
        {section !== "upload" ? (
        <article className="legal-tools-v2__research-card p-5">
          <h3 className="font-semibold m-0">My documents</h3>
          <p className="text-sm text-slate-500 mt-2 m-0">Shared firm documents appear here after portal link is issued.</p>
        </article>
        ) : null}
        {section === "upload" && (
        <article className="legal-tools-v2__research-card p-5 space-y-3 lg:col-span-2">
          <h3 className="font-semibold m-0">Client upload center</h3>
          <p className="text-xs text-slate-500 m-0">Evidence, ID, agreements, and orders — auto-linked to matter.</p>
          <div className="grid grid-cols-2 gap-2">
            {CLIENT_UPLOAD_TYPES.map((t) => (
              <button
                key={t}
                type="button"
                onClick={() => setUploadType(t)}
                className={`px-3 py-2 rounded-lg border text-sm text-left ${
                  uploadType === t ? "border-navy bg-slate-900 text-white" : "hover:bg-slate-50"
                }`}
              >
                Upload {t}
              </button>
            ))}
          </div>
          <select
            className="w-full border rounded-lg px-3 py-2 text-sm"
            value={reqType}
            onChange={(e) =>
              setReqType(e.target.value as (typeof DOC_REQUEST_TYPES)[number])
            }
          >
            {DOC_REQUEST_TYPES.map((t) => (
              <option key={t} value={t}>
                Request: {t}
              </option>
            ))}
          </select>
          <button
            type="button"
            disabled={busy || !matterId}
            onClick={sendDocRequest}
            className="w-full px-4 py-2 bg-navy text-white rounded-lg text-sm disabled:opacity-50"
          >
            Request from client
          </button>
        </article>
        )}
      </div>
      )}

      {(section === "approvals" || section === "tasks") && (
      <article className="legal-tools-v2__research-card p-5 space-y-3">
        <h3 className="font-semibold m-0">
          {section === "tasks" ? "Client tasks" : "Approval workflow"}
        </h3>
        {section === "tasks" && (
          <p className="text-xs text-slate-500 m-0">Approve draft · Request changes · Sign document</p>
        )}
        <div className="flex flex-wrap gap-2">
          <input
            className="flex-1 min-w-[200px] border rounded-lg px-3 py-2 text-sm"
            placeholder="Draft title"
            value={reviewTitle}
            onChange={(e) => setReviewTitle(e.target.value)}
          />
          <button
            type="button"
            disabled={busy || !matterId || !reviewTitle.trim()}
            onClick={sendReview}
            className="px-4 py-2 border border-navy text-navy rounded-lg text-sm disabled:opacity-50"
          >
            Request client review
          </button>
        </div>
        {msg && <p className="text-sm text-emerald-700 m-0">{msg}</p>}
      </article>
      )}

      {section === "invoices" && (
        <article className="legal-tools-v2__research-card p-5">
          <h3 className="font-semibold m-0">Invoices</h3>
          <p className="text-sm text-slate-500 mt-2 m-0">Client billing view connects to firm billing module.</p>
        </article>
      )}

      {data && (section === "dashboard" || section === "approvals") && (
        <div className="grid md:grid-cols-2 gap-4">
          <section className="legal-tools-v2__research-card p-5">
            <h3 className="font-semibold m-0">Portal accounts</h3>
            <ul className="mt-3 space-y-2 text-sm list-none p-0 m-0">
              {data.portals.length === 0 && <li className="text-slate-500">No active portal links.</li>}
              {data.portals.map((p) => (
                <li key={String(p.access_id)} className="flex justify-between border-b py-2 gap-2">
                  <span className="truncate">{String(p.client_email)}</span>
                  <span className="text-slate-400 text-xs shrink-0">
                    exp. {String(p.expires_at).slice(0, 10)}
                  </span>
                </li>
              ))}
            </ul>
          </section>
          <section className="legal-tools-v2__research-card p-5">
            <h3 className="font-semibold m-0">Pending workflows</h3>
            <div className="mt-3 space-y-2 text-sm max-h-48 overflow-y-auto le-scroll">
              {data.document_requests.map((r) => (
                <div key={String(r.request_id)} className="py-2 border-b">
                  {String(r.request_type)} — <span className="text-amber-700">{String(r.status)}</span>
                </div>
              ))}
              {data.approvals.map((a) => (
                <div key={String(a.approval_id)} className="py-2 border-b">
                  {String(a.title)} — <span className="text-blue-700">{String(a.status)}</span>
                </div>
              ))}
            </div>
          </section>
        </div>
      )}
    </div>
  );
}

export function DocumentCenterModule({ matters }: { matters: api.Matter[] }) {
  const [docs, setDocs] = useState<Array<Record<string, unknown>>>([]);
  const [folders, setFolders] = useState<Array<Record<string, unknown>>>([]);
  const [matterId, setMatterId] = useState("");
  const [practiceArea, setPracticeArea] = useState("Litigation");
  const [searchQ, setSearchQ] = useState("");
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [busy, setBusy] = useState(false);
  const [dupWarn, setDupWarn] = useState("");

  const refresh = useCallback(() => {
    api
      .fetchEnterpriseDocuments({ matter_id: matterId, practice_area: practiceArea })
      .then((r) => setDocs(r.documents || []))
      .catch(() => setDocs([]));
    api
      .fetchEnterpriseFolders(matterId, practiceArea)
      .then((r) => setFolders(r.folders || []))
      .catch(() => setFolders([]));
  }, [matterId, practiceArea]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const seedFolders = async () => {
    const m = matters.find((x) => x.matter_id === matterId);
    if (!m) return;
    setBusy(true);
    await api.seedEnterpriseMatterFolders(matterId, m.matter_name, practiceArea);
    refresh();
    setBusy(false);
  };

  const upload = async () => {
    if (!title.trim() || !content.trim()) return;
    setBusy(true);
    setDupWarn("");
    try {
      const r = await api.uploadEnterpriseDocument({
        title,
        content_text: content,
        matter_id: matterId,
        practice_area: practiceArea,
        doc_type: "General",
      });
      if (r.duplicate_warning) {
        const w = r.duplicate_warning as Record<string, unknown>;
        setDupWarn(`Possible duplicate of “${String(w.title)}” — flagged for review.`);
      }
      setTitle("");
      setContent("");
      refresh();
    } finally {
      setBusy(false);
    }
  };

  const runSearch = async () => {
    const r = await api.searchEnterpriseDocuments(searchQ, { matter_id: matterId });
    setDocs(r.results || []);
  };

  return (
    <div className="space-y-6">
      <article className="legal-tools-v2__research-card p-6 space-y-4">
        <h2 className="font-serif text-xl font-bold text-navy m-0">Document Management</h2>
        <div className="grid sm:grid-cols-3 gap-3">
          <label className="text-sm">
            Practice area
            <select
              className="mt-1 w-full border rounded-lg px-3 py-2"
              value={practiceArea}
              onChange={(e) => setPracticeArea(e.target.value)}
            >
              {PRACTICE_AREAS.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
          </label>
          <label className="text-sm sm:col-span-2">
            Matter
            <select
              className="mt-1 w-full border rounded-lg px-3 py-2"
              value={matterId}
              onChange={(e) => setMatterId(e.target.value)}
            >
              <option value="">All matters</option>
              {matters.map((m) => (
                <option key={m.matter_id} value={m.matter_id}>
                  {m.matter_name}
                </option>
              ))}
            </select>
          </label>
        </div>
        {matterId && (
          <button
            type="button"
            disabled={busy}
            onClick={seedFolders}
            className="text-sm px-3 py-1.5 border rounded-lg hover:bg-slate-50"
          >
            Initialize matter folders (Pleadings, Orders, Evidence…)
          </button>
        )}
        <div className="flex gap-2">
          <input
            className="flex-1 legal-tools-v2__search-input"
            placeholder="Global DMS search — keyword, tag, matter…"
            value={searchQ}
            onChange={(e) => setSearchQ(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && runSearch()}
          />
          <button type="button" onClick={runSearch} className="px-4 py-2 bg-navy text-white rounded-lg text-sm">
            Search
          </button>
        </div>
      </article>

      <div className="grid lg:grid-cols-[220px_1fr] gap-4">
        <aside className="legal-tools-v2__research-card p-4">
          <p className="text-xs font-bold uppercase text-slate-500 m-0">Folder tree</p>
          {matterId ? (
            <ul className="ent-folder-tree mt-2">
              <li className="font-semibold text-navy">Matter</li>
              {FOLDER_TYPES.map((ft) => {
                const match = folders.find((f) => String(f.folder_name) === ft);
                return (
                  <li key={ft}>
                    {ft}
                    {match && <span className="text-slate-400 text-xs ml-1">· indexed</span>}
                  </li>
                );
              })}
            </ul>
          ) : (
            <p className="text-xs text-slate-500 mt-2 m-0">Select a matter to view Orders / Evidence / Pleadings / Drafts.</p>
          )}
          {folders.length > 0 && (
            <ul className="mt-3 space-y-1 text-xs text-slate-500 list-none p-0 m-0 border-t pt-2">
              {folders.map((f) => (
                <li key={String(f.folder_id)}>{String(f.folder_name)}</li>
              ))}
            </ul>
          )}
        </aside>
        <div className="space-y-4">
          <article className="legal-tools-v2__research-card p-5 space-y-3">
            <h3 className="font-semibold m-0">Upload document</h3>
            <input
              className="w-full border rounded-lg px-3 py-2 text-sm"
              placeholder="Title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />
            <VoiceTextarea
              value={content}
              onChange={setContent}
              rows={6}
              placeholder="Paste document text or OCR output…"
              className="w-full border rounded-lg px-3 py-2 text-sm font-mono"
            />
            <button
              type="button"
              disabled={busy}
              onClick={upload}
              className="px-4 py-2 bg-navy text-white rounded-lg text-sm disabled:opacity-50"
            >
              Upload & index
            </button>
            {dupWarn && (
              <p className="text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 m-0">
                {dupWarn}
              </p>
            )}
          </article>
          <section className="space-y-2">
            {docs.map((d) => (
              <div key={String(d.doc_id)} className="legal-tools-v2__research-card p-4 flex justify-between gap-4">
                <div>
                  <p className="font-semibold text-navy m-0">{String(d.title)}</p>
                  <p className="text-xs text-slate-500 m-0 mt-1">
                    {Array.from({ length: Math.max(1, Number(d.version_no) || 1) }, (_, i) => `v${i + 1}`).join(" · ")}{" "}
                    · {String(d.doc_type)} · OCR {(Number(d.ocr_confidence) * 100).toFixed(0)}%
                  </p>
                  {"snippet" in d && (
                    <p className="text-xs text-slate-600 mt-2 m-0 line-clamp-2">{String(d.snippet)}</p>
                  )}
                </div>
                <span className="text-[10px] text-slate-400 shrink-0">{String(d.updated_at).slice(0, 10)}</span>
              </div>
            ))}
            {docs.length === 0 && (
              <p className="text-sm text-slate-500 text-center py-8">No documents — upload to build your DMS.</p>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}

export function CourtOrdersModule({ matters }: { matters: api.Matter[] }) {
  const [orders, setOrders] = useState<Array<Record<string, unknown>>>([]);
  const [selected, setSelected] = useState<Record<string, unknown> | null>(null);
  const [matterId, setMatterId] = useState("");
  const [text, setText] = useState("");
  const [orderType, setOrderType] = useState("order");
  const [searchQ, setSearchQ] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api.fetchEnterpriseCourtOrders(matterId).then((r) => setOrders(r.orders || []));
  }, [matterId]);

  useEffect(() => {
    load();
  }, [load]);

  const upload = async () => {
    if (text.trim().length < 20) return;
    setBusy(true);
    try {
      const o = await api.uploadEnterpriseCourtOrder({
        content_text: text,
        matter_id: matterId,
        order_type: orderType,
      });
      setText("");
      setSelected(o);
      load();
    } finally {
      setBusy(false);
    }
  };

  const search = async () => {
    const r = await api.searchEnterpriseCourtOrders(searchQ, { matter_id: matterId });
    setOrders(r.results || []);
  };

  return (
    <div className="space-y-6">
      <article className="legal-tools-v2__research-card p-6 space-y-4">
        <h2 className="font-serif text-xl font-bold text-navy m-0">Court Order Repository</h2>
        <p className="text-sm text-slate-600 m-0">
          Upload orders for OCR, metadata extraction, AI summary, directions, and deadlines.
        </p>
        <div className="flex flex-wrap gap-2">
          <input
            className="flex-1 min-w-[200px] legal-tools-v2__search-input"
            placeholder="Search judge, court, case number, keyword…"
            value={searchQ}
            onChange={(e) => setSearchQ(e.target.value)}
          />
          <button type="button" onClick={search} className="px-4 py-2 border rounded-lg text-sm">
            Search
          </button>
        </div>
        <select
          className="w-full border rounded-lg px-3 py-2 text-sm"
          value={matterId}
          onChange={(e) => setMatterId(e.target.value)}
        >
          <option value="">All matters</option>
          {matters.map((m) => (
            <option key={m.matter_id} value={m.matter_id}>
              {m.matter_name}
            </option>
          ))}
        </select>
        <select
          className="w-full border rounded-lg px-3 py-2 text-sm"
          value={orderType}
          onChange={(e) => setOrderType(e.target.value)}
        >
          {ORDER_TYPES.map((t) => (
            <option key={t.id} value={t.id}>
              {t.label}
            </option>
          ))}
        </select>
        <VoiceTextarea
          value={text}
          onChange={setText}
          rows={10}
          placeholder="Paste court order / judgment text…"
          className="w-full border rounded-lg px-3 py-2 text-sm font-mono"
        />
        <button
          type="button"
          disabled={busy || text.trim().length < 20}
          onClick={upload}
          className="px-4 py-2 bg-navy text-white rounded-lg text-sm disabled:opacity-50"
        >
          {busy ? "Processing…" : "Upload & analyze"}
        </button>
      </article>

      <div className="grid lg:grid-cols-2 gap-4">
        <div className="space-y-2 max-h-[480px] overflow-y-auto le-scroll">
          {orders.map((o) => (
            <button
              key={String(o.order_id)}
              type="button"
              onClick={async () => {
                try {
                  const full = await api.fetchEnterpriseCourtOrder(String(o.order_id));
                  setSelected(full);
                } catch {
                  setSelected(o);
                }
              }}
              className="w-full text-left legal-tools-v2__research-card p-4 hover:ring-2 hover:ring-slate-200"
            >
              <p className="font-semibold text-navy m-0 text-sm">{String(o.case_number || o.filename || "Order")}</p>
              <p className="text-xs text-slate-500 m-0 mt-1">
                {String(o.court)} · {String(o.judge)} · {String(o.order_date)}
              </p>
              <p className="text-xs text-slate-600 mt-2 m-0 line-clamp-2">{String(o.summary)}</p>
            </button>
          ))}
        </div>
        {selected && (() => {
          const riskLevel = String(
            selected.risk_level ||
              (selected.intelligence as Record<string, unknown> | undefined)?.risk_level ||
              ""
          );
          return (
          <article className="legal-tools-v2__research-card p-5 space-y-3 sticky top-4 max-h-[520px] overflow-y-auto le-scroll">
            <div className="flex justify-between items-start gap-2">
              <h3 className="font-serif font-bold m-0">Court order intelligence</h3>
              {riskLevel ? (
                <span
                  className={`text-[10px] font-bold uppercase px-2 py-1 rounded ${
                    riskLevel === "high"
                      ? "bg-red-100 text-red-800"
                      : riskLevel === "medium"
                        ? "bg-amber-100 text-amber-800"
                        : "bg-emerald-100 text-emerald-800"
                  }`}
                >
                  Risk: {riskLevel}
                </span>
              ) : null}
            </div>
            {(() => {
              const intel = (selected.intelligence as Record<string, unknown>) || {};
              const summary = String(intel.case_summary || selected.summary || "");
              const blocks: Array<[string, string[] | string]> = [
                ["Case summary", summary ? [summary] : []],
                ["Court directions", (intel.court_directions as string[]) || (selected.directions as string[]) || []],
                ["Required actions", (intel.required_actions as string[]) || (selected.next_steps as string[]) || []],
                ["Deadlines", (selected.deadlines as string[]) || []],
                ["Affected parties", (intel.affected_parties as string[]) || []],
                ["Next hearing", intel.next_hearing ? [String(intel.next_hearing)] : []],
                ["Risks", (selected.risks as string[]) || []],
              ];
              return (
                <div className="ent-intel-grid">
                  {blocks.map(([label, val]) => {
                    const lines = Array.isArray(val) ? val : val ? [val] : [];
                    if (!lines.length) return null;
                    return (
                      <div key={label} className="ent-intel-card sm:col-span-2">
                        <p className="text-[10px] font-bold uppercase text-slate-500 m-0">{label}</p>
                        {lines.length === 1 && label === "Case summary" ? (
                          <p className="text-sm m-0 mt-1">{lines[0]}</p>
                        ) : (
                          <ul className="text-sm mt-1 list-disc pl-4 m-0">
                            {lines.map((line, i) => (
                              <li key={i}>{line}</li>
                            ))}
                          </ul>
                        )}
                      </div>
                    );
                  })}
                </div>
              );
            })()}
          </article>
          );
        })()}
      </div>
    </div>
  );
}

export function KnowledgeModule() {
  const [q, setQ] = useState("bail orders");
  const [results, setResults] = useState<Array<Record<string, unknown>>>([]);
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");

  const search = async () => {
    const r = await api.searchEnterpriseKnowledge(q);
    setResults(r.results || []);
  };

  useEffect(() => {
    search();
  }, []);

  const add = async () => {
    if (!title.trim()) return;
    await api.createEnterpriseKnowledge({ title, content_text: content, entry_type: "memo" });
    setTitle("");
    setContent("");
    search();
  };

  return (
    <div className="space-y-6">
      <article className="legal-tools-v2__research-card p-6 space-y-4">
        <h2 className="font-serif text-xl font-bold text-navy m-0">Firm Knowledge Base</h2>
        <div className="flex gap-2">
          <input
            className="flex-1 legal-tools-v2__search-input"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="e.g. Show all bail orders, Delhi High Court, Section 302…"
          />
          <button type="button" onClick={search} className="px-4 py-2 bg-navy text-white rounded-lg text-sm">
            AI search
          </button>
        </div>
      </article>
      <div className="grid md:grid-cols-2 gap-4">
        <section className="space-y-2">
          {results.map((e) => (
            <div key={String(e.entry_id)} className="legal-tools-v2__research-card p-4">
              <p className="font-semibold m-0">{String(e.title)}</p>
              <p className="text-[10px] uppercase text-slate-500 m-0 mt-1">
                {String(e.entry_type)} · {String(e.court || e.practice_area)}
              </p>
              <p className="text-xs text-slate-600 mt-2 m-0 line-clamp-3">{String(e.snippet)}</p>
            </div>
          ))}
        </section>
        <article className="legal-tools-v2__research-card p-5 space-y-3">
          <h3 className="font-semibold m-0">Add research note</h3>
          <input
            className="w-full border rounded-lg px-3 py-2 text-sm"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Title"
          />
          <VoiceTextarea
            value={content}
            onChange={setContent}
            rows={5}
            className="w-full border rounded-lg px-3 py-2 text-sm"
          />
          <button type="button" onClick={add} className="px-4 py-2 border rounded-lg text-sm">
            Save to knowledge base
          </button>
        </article>
      </div>
    </div>
  );
}

export function AgentsModule({
  agents,
  matters,
  selectedMatter,
  onMatterChange,
  onRun,
  onRunAll,
  busy,
  result,
  err,
}: {
  agents: AgentStatus[];
  matters: api.Matter[];
  selectedMatter: string;
  onMatterChange: (id: string) => void;
  onRun: (id: string) => void;
  onRunAll?: () => void;
  busy: boolean;
  result: Record<string, unknown> | null;
  err: string;
}) {
  const running = agents.filter((a) => a.status === "running").length;

  return (
    <div className="space-y-5">
      <article className="legal-tools-v2__research-card p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h2 className="font-serif text-xl font-bold text-navy m-0">Autonomous AI agents</h2>
            <p className="text-sm text-slate-600 mt-2 m-0">
              Agents run on schedule or triggers — not one-off buttons. {running > 0 && (
                <span className="text-emerald-700 font-medium">{running} running now</span>
              )}
            </p>
          </div>
          {onRunAll && (
            <button
              type="button"
              disabled={busy}
              onClick={onRunAll}
              className="px-4 py-2 bg-navy text-white rounded-lg text-sm disabled:opacity-50"
            >
              Run compliance sweep
            </button>
          )}
        </div>
        <label className="block text-sm mt-4 max-w-md">
          Default matter context
          <select
            className="mt-1 w-full border rounded-lg px-3 py-2"
            value={selectedMatter}
            onChange={(e) => onMatterChange(e.target.value)}
          >
            <option value="">— Firm-wide —</option>
            {matters.map((m) => (
              <option key={m.matter_id} value={m.matter_id}>
                {m.matter_name}
              </option>
            ))}
          </select>
        </label>
      </article>

      <div className="grid sm:grid-cols-2 xl:grid-cols-3 gap-4">
        {agents.map((a) => (
          <article
            key={a.id}
            className={`ent-agent-card legal-tools-v2__research-card p-5 ${
              a.status === "running" ? "ent-agent-card--running" : ""
            }`}
          >
            <div className="flex items-start justify-between gap-2">
              <p className="font-semibold text-navy m-0">{a.name}</p>
              <span
                className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded-full ${
                  a.status === "running"
                    ? "bg-emerald-100 text-emerald-800"
                    : "bg-slate-100 text-slate-600"
                }`}
              >
                {a.status}
              </span>
            </div>
            <p className="text-xs text-slate-600 mt-2 m-0">{a.description}</p>
            <p className="text-[10px] text-slate-400 mt-2 m-0">
              {a.mode === "autonomous" ? "Autonomous" : "Manual"} · {a.schedule || "On demand"}
            </p>
            <button
              type="button"
              disabled={busy || a.status === "running"}
              onClick={() => onRun(a.id)}
              className="mt-4 w-full px-3 py-2 border rounded-lg text-sm hover:bg-slate-50 disabled:opacity-50"
            >
              {a.status === "running" ? "Running…" : "Run now"}
            </button>
          </article>
        ))}
      </div>
      {err && <p className="text-sm text-red-600 m-0">{err}</p>}
      {result && (
        <pre className="text-xs bg-slate-50 border rounded-lg p-4 overflow-auto max-h-48">
          {JSON.stringify(result, null, 2)}
        </pre>
      )}
    </div>
  );
}

export function AutomationModule({
  causeText,
  onCauseChange,
  onSync,
  busy,
}: {
  causeText: string;
  onCauseChange: (v: string) => void;
  onSync: () => void;
  busy: boolean;
}) {
  return (
    <article className="legal-tools-v2__research-card p-6 space-y-4">
      <h2 className="font-serif text-xl font-bold text-navy m-0">Automation</h2>
      <p className="text-sm text-slate-600 m-0">Court cause list sync — match matters and schedule hearings.</p>
      <VoiceTextarea
        value={causeText}
        onChange={onCauseChange}
        rows={10}
        placeholder="Paste cause list from eCourts…"
        className="w-full border rounded-lg px-3 py-2 text-sm font-mono"
      />
      <button
        type="button"
        disabled={busy || !causeText.trim()}
        onClick={onSync}
        className="px-4 py-2 bg-navy text-white rounded-lg text-sm disabled:opacity-50"
      >
        Sync & schedule
      </button>
    </article>
  );
}

export function MatterHubModule({
  matters,
  initialMatterId,
}: {
  matters: api.Matter[];
  initialMatterId?: string;
}) {
  const [matterId, setMatterId] = useState(initialMatterId || "");
  const [hub, setHub] = useState<Record<string, unknown> | null>(null);

  useEffect(() => {
    if (initialMatterId) setMatterId(initialMatterId);
  }, [initialMatterId]);

  useEffect(() => {
    if (!matterId) {
      setHub(null);
      return;
    }
    api.fetchEnterpriseMatterHub(matterId).then(setHub).catch(() => setHub(null));
  }, [matterId]);

  const tree = (hub?.tree as { children?: Array<Record<string, unknown>> })?.children || [];
  const timeline = (hub?.timeline as Array<Record<string, unknown>>) || [];

  return (
    <div className="space-y-5">
      <article className="legal-tools-v2__research-card p-5">
        <h2 className="font-serif text-xl font-bold text-navy m-0">Matter-centric workspace</h2>
        <select
          className="mt-3 w-full border rounded-lg px-3 py-2"
          value={matterId}
          onChange={(e) => setMatterId(e.target.value)}
        >
          <option value="">Select matter</option>
          {matters.map((m) => (
            <option key={m.matter_id} value={m.matter_id}>
              {m.matter_name}
            </option>
          ))}
        </select>
      </article>
      {hub && (
        <div className="grid lg:grid-cols-[240px_1fr] gap-4">
          <aside className="legal-tools-v2__research-card p-4">
            <p className="text-xs font-bold uppercase text-slate-500 m-0">Matter tree</p>
            <ul className="mt-3 space-y-1 list-none m-0 p-0 text-sm">
              {tree.map((n) => (
                <li key={String(n.key)} className="py-1.5 border-b border-slate-50">
                  <span className="font-medium">{String(n.label)}</span>
                  {n.count != null && (
                    <span className="text-slate-400 ml-1">({String(n.count)})</span>
                  )}
                </li>
              ))}
            </ul>
          </aside>
          <div className="space-y-4">
            <article className="legal-tools-v2__research-card p-5">
              <h3 className="font-semibold m-0">Timeline</h3>
              {timeline.length === 0 && (
                <p className="text-sm text-slate-500 mt-2 m-0">Events appear when you upload, sync, or approve.</p>
              )}
              <ul className="mt-3 space-y-3 list-none m-0 p-0">
                {timeline.map((ev) => (
                  <li key={String(ev.event_id)} className="flex gap-3 text-sm border-l-2 border-slate-200 pl-3">
                    <span className="text-slate-400 shrink-0 w-20">{String(ev.event_date)}</span>
                    <span>
                      <strong className="text-navy">{String(ev.title)}</strong>
                      {ev.description != null && String(ev.description) !== "" ? (
                        <span className="block text-slate-500 text-xs mt-0.5">{String(ev.description)}</span>
                      ) : null}
                    </span>
                  </li>
                ))}
              </ul>
            </article>
          </div>
        </div>
      )}
    </div>
  );
}

export function AnalyticsModule({ data }: { data?: Record<string, unknown> }) {
  const firm = (data?.firm as Record<string, number>) || {};
  const lit = (data?.litigation as Record<string, number>) || {};
  return (
    <div className="space-y-5">
      <article className="legal-tools-v2__research-card p-6">
        <h2 className="font-serif text-xl font-bold text-navy m-0">Firm analytics</h2>
        <div className="mt-4 legal-tools-v2__stat-grid">
          {[
            ["Open matters", firm.open_matters],
            ["Closed matters", firm.closed_matters],
            ["Documents", firm.total_documents],
            ["Court orders", firm.total_orders],
            ["Storage (MB)", firm.storage_mb],
          ].map(([k, v]) => (
            <div key={String(k)} className="legal-tools-v2__stat">
              <p className="text-[10px] uppercase text-slate-500 m-0">{String(k)}</p>
              <p className="text-xl font-bold m-0 mt-1">{String(v ?? "—")}</p>
            </div>
          ))}
        </div>
      </article>
      <article className="legal-tools-v2__research-card p-6">
        <h3 className="font-semibold m-0">Litigation metrics</h3>
        <div className="mt-3 grid sm:grid-cols-3 gap-3">
          <div className="legal-tools-v2__stat">
            <p className="text-[10px] uppercase text-slate-500 m-0">Hearings this month</p>
            <p className="text-xl font-bold m-0">{String(lit.hearings_this_month ?? "—")}</p>
          </div>
          <div className="legal-tools-v2__stat">
            <p className="text-[10px] uppercase text-slate-500 m-0">Orders received</p>
            <p className="text-xl font-bold m-0">{String(lit.orders_received ?? "—")}</p>
          </div>
          <div className="legal-tools-v2__stat">
            <p className="text-[10px] uppercase text-slate-500 m-0">Compliance rate</p>
            <p className="text-xl font-bold m-0">{String(lit.compliance_rate_pct ?? "—")}%</p>
          </div>
        </div>
      </article>
    </div>
  );
}

export function ComplianceModule({ matters }: { matters: api.Matter[] }) {
  const [audit, setAudit] = useState<Array<Record<string, unknown>>>([]);
  const [q, setQ] = useState("");

  useEffect(() => {
    api.fetchEnterpriseAudit().then((r) => setAudit(r.entries || []));
  }, []);

  const search = () => {
    api.fetchEnterpriseAudit(q).then((r) => setAudit(r.entries || []));
  };

  return (
    <div className="space-y-6">
      <article className="legal-tools-v2__research-card p-6">
        <h2 className="font-serif text-xl font-bold text-navy m-0">Compliance & audit</h2>
        <p className="text-sm text-slate-600 m-0">
          Searchable audit trail — uploads, downloads, shares, edits, approvals.
        </p>
        <div className="flex gap-2 mt-4">
          <input
            className="flex-1 legal-tools-v2__search-input"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Filter audit log…"
          />
          <button type="button" onClick={search} className="px-4 py-2 border rounded-lg text-sm">
            Search
          </button>
        </div>
      </article>
      <div className="legal-tools-v2__research-card overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-left">
            <tr>
              <th className="px-4 py-2">Time</th>
              <th className="px-4 py-2">Action</th>
              <th className="px-4 py-2">Resource</th>
            </tr>
          </thead>
          <tbody>
            {audit.map((e) => (
              <tr key={String(e.audit_id)} className="border-t">
                <td className="px-4 py-2 text-xs text-slate-500">{String(e.created_at).slice(0, 19)}</td>
                <td className="px-4 py-2">{String(e.action)}</td>
                <td className="px-4 py-2 text-slate-600">
                  {String(e.resource_type)} {String(e.resource_id).slice(0, 8)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {audit.length === 0 && <p className="p-6 text-sm text-slate-500 m-0">No audit entries yet.</p>}
      </div>
      <p className="text-xs text-slate-500">
        Open matters for deadline tracking: {matters.filter((m) => m.next_hearing_date).length} with hearings
        scheduled.
      </p>
    </div>
  );
}

function StatCard({ label, value, sub }: { label: string; value: string | number; sub?: string }) {
  return (
    <div className="legal-tools-v2__stat">
      <p className="text-[10px] uppercase text-slate-500 m-0">{label}</p>
      <p className="text-xl font-bold text-slate-900 m-0 mt-1">{value}</p>
      {sub && <p className="text-[11px] text-slate-500 m-0 mt-1">{sub}</p>}
    </div>
  );
}

export function StorageModule() {
  const [storage, setStorage] = useState<Record<string, unknown> | null>(null);

  useEffect(() => {
    api.fetchEnterpriseStorage().then(setStorage).catch(() => setStorage(null));
  }, []);

  const pct = Number(storage?.percent_used ?? 0);
  return (
    <article className="legal-tools-v2__research-card p-6 space-y-4">
      <h2 className="font-serif text-xl font-bold text-navy m-0">Storage</h2>
      {storage && (
        <>
          <div className="h-3 rounded-full bg-slate-100 overflow-hidden">
            <div className="h-full bg-navy rounded-full transition-all" style={{ width: `${Math.min(pct, 100)}%` }} />
          </div>
          <div className="legal-tools-v2__stat-grid">
            <StatCard label="Used" value={`${storage.mb_used} MB`} />
            <StatCard label="Quota" value={`${storage.quota_gb} GB`} />
            <StatCard label="Documents" value={Number(storage.document_count)} />
            <StatCard label="Orders" value={Number(storage.order_count)} />
          </div>
        </>
      )}
    </article>
  );
}
