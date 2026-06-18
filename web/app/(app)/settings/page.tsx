"use client";

import { useCallback, useEffect, useState } from "react";
import PageHeader from "@/components/ui/PageHeader";
import MemoryPanel from "@/components/settings/MemoryPanel";
import { useAuth } from "@/components/providers/AuthProvider";
import { useLearnerMode } from "@/hooks/useLearnerMode";
import * as api from "@/lib/api";
import type { SettingsPayload } from "@/lib/api";

export default function SettingsPage() {
  const { user, refreshUser } = useAuth();
  const { learnerMode, setLearnerMode } = useLearnerMode();
  const [settings, setSettings] = useState<SettingsPayload | null>(null);
  const [payments, setPayments] = useState<
    Array<{ plan: string; amount: number; status: string }>
  >([]);
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const [loadErr, setLoadErr] = useState("");
  const [deleteUser, setDeleteUser] = useState("");
  const [deletePass, setDeletePass] = useState("");

  const load = useCallback(() => {
    setLoadErr("");
    api
      .fetchSettings()
      .then(setSettings)
      .catch((e) => setLoadErr(e.message));
    api
      .fetchPayments()
      .then((d) => setPayments(d.payments || []))
      .catch(() => setPayments([]));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const upgrade = async (plan: string) => {
    setBusy(true);
    setMsg("");
    try {
      await api.upgradePlan(plan);
      await refreshUser();
      setMsg(`Upgraded to ${plan}!`);
      load();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "Upgrade failed");
    } finally {
      setBusy(false);
    }
  };

  const llm = settings?.llm || {};

  return (
    <div className="flex flex-col h-full min-h-0">
      <PageHeader
        title="Settings"
        subtitle="Account, plans, and system configuration"
      />
      <div className="flex-1 overflow-y-auto overflow-x-hidden le-scroll le-page-body max-w-3xl mx-auto w-full space-y-6 sm:space-y-8">
        {loadErr && (
          <p className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-4 py-3">
            {loadErr}
          </p>
        )}

        <MemoryPanel />

        <section className="bg-white rounded-2xl border border-slate-200 p-6">
          <h2 className="font-semibold text-navy mb-2">Learner mode</h2>
          <p className="text-sm text-slate-600 mb-4">
            Simpler AI language; hides firm tools (Litigation Desk, billing, CRM).
          </p>
          <label className="flex items-center gap-3 cursor-pointer">
            <input
              type="checkbox"
              checked={learnerMode}
              onChange={async (e) => {
                setBusy(true);
                try {
                  await setLearnerMode(e.target.checked);
                  setMsg(e.target.checked ? "Learner mode enabled" : "Learner mode disabled");
                } catch (err) {
                  setMsg(err instanceof Error ? err.message : "Could not update preference");
                } finally {
                  setBusy(false);
                }
              }}
              className="w-4 h-4"
            />
            <span className="text-sm font-medium">Enable learner mode</span>
          </label>
        </section>

        <section className="bg-white rounded-2xl border border-slate-200 p-6">
          <h2 className="font-semibold text-navy mb-3">Team & subscription</h2>
          <div className="flex flex-wrap gap-2">
            <a
              href="/settings/team"
              className="px-4 py-2 border border-slate-300 rounded-lg text-sm font-semibold hover:bg-slate-50"
            >
              Manage team
            </a>
            <a
              href="/settings/subscription"
              className="px-4 py-2 border border-slate-300 rounded-lg text-sm font-semibold hover:bg-slate-50"
            >
              Subscription & usage
            </a>
            <a
              href="/onboarding"
              className="px-4 py-2 border border-slate-300 rounded-lg text-sm font-semibold hover:bg-slate-50"
            >
              Setup checklist
            </a>
          </div>
        </section>

        <section className="bg-white rounded-2xl border border-slate-200 p-6">
          <h2 className="font-semibold text-navy mb-3">Profile</h2>
          <p className="text-sm">
            <b>Username:</b> {user?.username}
          </p>
          <p className="text-sm mt-1">
            <b>Role:</b> {user?.role || "user"}
          </p>
          <span className="inline-block mt-2 text-xs font-bold px-3 py-1 rounded-full bg-blue-100 text-blue-800">
            {user?.membership}
          </span>
        </section>

        <section className="bg-white rounded-2xl border border-slate-200 p-6">
          <h2 className="font-semibold text-navy mb-3">
            LLM — {String(llm.backend || "LM Studio")}
          </h2>
          <p className="text-sm text-slate-600">
            Model: <code className="text-xs bg-slate-100 px-1 rounded">{String(llm.model || "—")}</code>
          </p>
          <p
            className={`text-sm mt-2 ${
              llm.available || llm.online ? "text-emerald-600" : "text-red-600"
            }`}
          >
            {String(llm.message || llm.status || "Unknown")}
          </p>
          <div className="flex gap-2 mt-4">
            <button
              type="button"
              disabled={busy}
              onClick={async () => {
                setBusy(true);
                try {
                  await api.recheckLlm();
                  load();
                  setMsg("LLM status rechecked.");
                } catch (e) {
                  setMsg(e instanceof Error ? e.message : "Recheck failed");
                } finally {
                  setBusy(false);
                }
              }}
              className="px-3 py-2 border border-slate-300 rounded-lg text-xs font-semibold hover:bg-slate-50 disabled:opacity-50"
            >
              Recheck
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={async () => {
                setBusy(true);
                try {
                  const r = await api.testLlm();
                  setMsg(`Test: ${r.reply}`);
                } catch (e) {
                  setMsg(e instanceof Error ? e.message : "Test failed");
                } finally {
                  setBusy(false);
                }
              }}
              className="px-3 py-2 bg-navy text-white rounded-lg text-xs font-semibold disabled:opacity-50"
            >
              Test prompt
            </button>
          </div>
        </section>

        <section className="bg-white rounded-2xl border border-red-200 p-6">
          <h2 className="font-semibold text-navy mb-3">Privacy & data (GDPR)</h2>
          <p className="text-sm text-slate-600 mb-4">
            Export a ZIP of your profile, chat history, matters, and document metadata. Account
            deletion is permanent and removes indexes, files, and chat data.
          </p>
          <div className="flex flex-wrap gap-2 mb-4">
            <button
              type="button"
              disabled={busy}
              onClick={async () => {
                setBusy(true);
                setMsg("");
                try {
                  const blob = await api.exportAccountZip();
                  const url = URL.createObjectURL(blob);
                  const a = document.createElement("a");
                  a.href = url;
                  a.download = `legalease-export-${user?.username || "data"}.zip`;
                  a.click();
                  URL.revokeObjectURL(url);
                  setMsg("Export downloaded.");
                } catch (e) {
                  setMsg(e instanceof Error ? e.message : "Export failed");
                } finally {
                  setBusy(false);
                }
              }}
              className="px-4 py-2 border border-slate-300 rounded-lg text-sm font-semibold hover:bg-slate-50 disabled:opacity-50"
            >
              Download my data
            </button>
            <a
              href="/onboarding"
              className="px-4 py-2 border border-slate-300 rounded-lg text-sm font-semibold hover:bg-slate-50 inline-flex items-center"
            >
              Setup checklist
            </a>
          </div>
          <div className="border-t border-red-100 pt-4 space-y-2">
            <p className="text-sm font-medium text-red-800">Delete account</p>
            <input
              className="w-full border rounded-lg px-3 py-2 text-sm"
              placeholder="Type username to confirm"
              value={deleteUser}
              onChange={(e) => setDeleteUser(e.target.value)}
            />
            <input
              type="password"
              className="w-full border rounded-lg px-3 py-2 text-sm"
              placeholder="Password"
              value={deletePass}
              onChange={(e) => setDeletePass(e.target.value)}
            />
            <button
              type="button"
              disabled={busy}
              onClick={async () => {
                if (!window.confirm("Permanently delete your account and all data?")) return;
                setBusy(true);
                setMsg("");
                try {
                  await api.deleteAccount(deleteUser, deletePass);
                  localStorage.removeItem("legalease_token");
                  window.location.href = "/login";
                } catch (e) {
                  setMsg(e instanceof Error ? e.message : "Delete failed");
                } finally {
                  setBusy(false);
                }
              }}
              className="px-4 py-2 bg-red-600 text-white rounded-lg text-sm font-semibold disabled:opacity-50"
            >
              Delete my account
            </button>
          </div>
        </section>

        <section className="bg-white rounded-2xl border border-slate-200 p-6 text-sm text-slate-600">
          <h2 className="font-semibold text-navy mb-2">Web & OCR</h2>
          <p>
            Tavily:{" "}
            {settings?.web_search?.tavily_configured ? "configured" : "not set"}
          </p>
          <p className="mt-1">
            OCR: {settings?.ocr?.enabled ? "enabled" : "disabled"}
          </p>
        </section>
      </div>
    </div>
  );
}
