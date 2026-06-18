"use client";

import { useCallback, useEffect, useState } from "react";
import PageHeader from "@/components/ui/PageHeader";
import { useAuth } from "@/components/providers/AuthProvider";
import * as api from "@/lib/api";

export default function AdminPage() {
  const { user } = useAuth();
  const [users, setUsers] = useState<Array<Record<string, unknown>>>([]);
  const [audit, setAudit] = useState<Array<Record<string, unknown>>>([]);
  const [usage, setUsage] = useState<Record<string, number>>({});
  const [health, setHealth] = useState<Record<string, string>>({});
  const [q, setQ] = useState("");
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");
  const [pilot, setPilot] = useState<{
    total: number;
    active: number;
    target: number;
    on_track: boolean;
    firms: Array<Record<string, unknown>>;
  } | null>(null);
  const [pilotName, setPilotName] = useState("");
  const [pilotEmail, setPilotEmail] = useState("");

  const load = useCallback(async () => {
    setErr("");
    try {
      const [u, a, us, h, p] = await Promise.all([
        api.adminListUsers(q),
        api.adminAudit(80),
        api.adminUsage(),
        api.adminHealth(),
        api.fetchPilotSummary().catch(() => null),
      ]);
      setUsers(u.users || []);
      setAudit(a.events || []);
      setUsage(us);
      setHealth(h);
      if (p) setPilot(p);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Admin access denied");
    }
  }, [q]);

  useEffect(() => {
    void load();
  }, [load]);

  const isAdmin =
    user?.role === "admin" ||
    user?.role === "superadmin" ||
    String(user?.username || "").toLowerCase() === "admin";

  if (!isAdmin) {
    return (
      <div className="le-page-body">
        <p className="text-red-600">Admin access required. Set SUPERADMIN_USERNAMES or role=admin.</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full min-h-0">
      <PageHeader title="Admin" subtitle="Users, audit trail, system health" />
      <div className="flex-1 overflow-y-auto overflow-x-hidden le-scroll le-page-body max-w-5xl mx-auto w-full space-y-4 sm:space-y-6">
        {err && (
          <p className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-4 py-3">
            {err}
          </p>
        )}
        {msg && <p className="text-sm text-green-700">{msg}</p>}

        <section className="bg-white border rounded-2xl p-4 grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
          {Object.entries(usage).map(([k, v]) => (
            <div key={k} className="p-3 bg-slate-50 rounded-lg">
              <p className="text-slate-500 text-xs">{k}</p>
              <p className="text-lg font-bold text-navy">{v}</p>
            </div>
          ))}
        </section>

        <section className="bg-white border rounded-2xl p-4 text-sm">
          <h2 className="font-semibold text-navy mb-2">System health</h2>
          <ul className="flex flex-wrap gap-2">
            {Object.entries(health).map(([k, v]) => (
              <li key={k} className="px-2 py-1 bg-slate-100 rounded">
                {k}: <b>{v}</b>
              </li>
            ))}
          </ul>
        </section>

        {pilot && (
          <section className="bg-white border rounded-2xl p-4 space-y-3">
            <h2 className="font-semibold text-navy">Pilot program</h2>
            <p className="text-sm text-slate-600">
              Active: <b>{pilot.active}</b> / target {pilot.target}
              {pilot.on_track ? " · on track" : " · need more firms"}
            </p>
            <div className="flex flex-wrap gap-2">
              <input
                className="border rounded-lg px-3 py-2 text-sm flex-1 min-w-[140px]"
                placeholder="Firm name"
                value={pilotName}
                onChange={(e) => setPilotName(e.target.value)}
              />
              <input
                className="border rounded-lg px-3 py-2 text-sm flex-1 min-w-[140px]"
                placeholder="contact@firm.com"
                value={pilotEmail}
                onChange={(e) => setPilotEmail(e.target.value)}
              />
              <button
                type="button"
                className="px-4 py-2 bg-navy text-white rounded-lg text-sm"
                onClick={async () => {
                  await api.registerPilotFirm({
                    firm_name: pilotName,
                    contact_email: pilotEmail,
                    plan: "Legal Pro",
                  });
                  setPilotName("");
                  setPilotEmail("");
                  setMsg("Pilot firm registered");
                  void load();
                }}
              >
                Add pilot
              </button>
            </div>
            <ul className="text-sm space-y-1">
              {(pilot.firms || []).map((f) => (
                <li key={String(f.pilot_id)} className="flex justify-between border-b py-1">
                  <span>{String(f.firm_name)}</span>
                  <span className="text-slate-500">{String(f.status)} · {String(f.plan)}</span>
                </li>
              ))}
            </ul>
          </section>
        )}

        <section className="bg-white border rounded-2xl p-4">
          <div className="flex gap-2 mb-3">
            <input
              className="border rounded-lg px-3 py-2 text-sm flex-1"
              placeholder="Search users…"
              value={q}
              onChange={(e) => setQ(e.target.value)}
            />
            <button
              type="button"
              onClick={() => void load()}
              className="px-4 py-2 bg-navy text-white rounded-lg text-sm"
            >
              Search
            </button>
          </div>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-slate-500">
                <th className="pb-2">User</th>
                <th>Plan</th>
                <th>Role</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={String(u.id)} className="border-t">
                  <td className="py-2">
                    {String(u.username)}
                    {u.suspended ? (
                      <span className="ml-1 text-xs text-red-600">suspended</span>
                    ) : null}
                  </td>
                  <td>{String(u.membership)}</td>
                  <td>{String(u.role)}</td>
                  <td className="space-x-1">
                    <button
                      type="button"
                      className="text-xs text-blue-700 underline"
                      onClick={async () => {
                        await api.adminSetPlan(String(u.id), "Pro");
                        setMsg(`Set ${u.username} to Pro`);
                        void load();
                      }}
                    >
                      Pro
                    </button>
                    <button
                      type="button"
                      className="text-xs text-amber-700 underline"
                      onClick={async () => {
                        if (u.suspended) {
                          await api.adminUnsuspend(String(u.id));
                        } else {
                          await api.adminSuspend(String(u.id));
                        }
                        void load();
                      }}
                    >
                      {u.suspended ? "Unsuspend" : "Suspend"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>

        <section className="bg-white border rounded-2xl p-4">
          <h2 className="font-semibold text-navy mb-2">Audit log</h2>
          <ul className="text-xs space-y-1 max-h-64 overflow-y-auto font-mono">
            {audit.map((e) => (
              <li key={String(e.id)} className="border-b border-slate-100 py-1">
                {String(e.created_at)} · {String(e.action)} · {String(e.user_id || "—")}{" "}
                {e.detail ? `· ${String(e.detail).slice(0, 80)}` : ""}
              </li>
            ))}
          </ul>
        </section>
      </div>
    </div>
  );
}
