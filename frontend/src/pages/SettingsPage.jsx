import { useEffect, useState } from "react";
import * as api from "../api/client.js";
import { useAuth } from "../context/AuthContext.jsx";
import PageHeader from "../components/PageHeader.jsx";

export default function SettingsPage() {
  const { user, setUser } = useAuth();
  const [settings, setSettings] = useState(null);
  const [payments, setPayments] = useState([]);
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  const load = () => {
    api.fetchSettings().then(setSettings).catch(() => {});
    api.fetchPayments().then((d) => setPayments(d.payments || [])).catch(() => {});
  };

  useEffect(() => {
    load();
  }, []);

  const upgrade = async (plan) => {
    setBusy(true);
    setMsg("");
    try {
      await api.upgradePlan(plan);
      const me = await api.fetchMe();
      setUser(me.user);
      api.updateStoredUser(me.user);
      setMsg(`Upgraded to ${plan}!`);
      load();
    } catch (e) {
      setMsg(e.message);
    } finally {
      setBusy(false);
    }
  };

  const llm = settings?.llm || {};

  return (
    <>
      <PageHeader title="Settings" subtitle="Account, plans, and system configuration" />
      <div className="flex-1 overflow-y-auto le-scroll p-8 max-w-3xl space-y-8">
        <section className="bg-white rounded-2xl border p-6">
          <h2 className="font-semibold text-navy mb-3">Profile</h2>
          <p className="text-sm"><b>Username:</b> {user?.username}</p>
          <p className="text-sm mt-1"><b>Role:</b> {user?.role}</p>
          <span className="inline-block mt-2 text-xs font-bold px-3 py-1 rounded-full bg-blue-100 text-blue-800">
            {user?.membership}
          </span>
        </section>

        <section className="bg-white rounded-2xl border p-6">
          <h2 className="font-semibold text-navy mb-3">Upgrade plan</h2>
          {user?.membership === "Free" && (
            <div className="p-4 rounded-xl bg-gradient-to-br from-blue-600 to-blue-800 text-white mb-3">
              <h3 className="font-bold">Pro — ₹999/year</h3>
              <p className="text-sm opacity-90 mt-1">Unlimited docs, Hybrid engine</p>
              <button type="button" disabled={busy} onClick={() => upgrade("Pro")} className="mt-3 px-4 py-2 bg-white text-blue-800 rounded-lg text-sm font-semibold">
                Upgrade to Pro
              </button>
            </div>
          )}
          {user?.membership === "Pro" && (
            <div className="p-4 rounded-xl bg-gradient-to-br from-amber-500 to-amber-700 text-white mb-3">
              <h3 className="font-bold">Legal Pro — ₹4999/year</h3>
              <button type="button" disabled={busy} onClick={() => upgrade("Legal Pro")} className="mt-3 px-4 py-2 bg-white text-amber-800 rounded-lg text-sm font-semibold">
                Upgrade to Legal Pro
              </button>
            </div>
          )}
          {user?.membership === "Legal Pro" && <p className="text-sm text-emerald-600">Highest plan active.</p>}
          {msg && <p className="text-sm mt-2 text-slate-600">{msg}</p>}
        </section>

        <section className="bg-white rounded-2xl border p-6">
          <h2 className="font-semibold text-navy mb-3">Payment history</h2>
          {payments.length ? (
            <table className="w-full text-sm">
              <thead><tr className="text-left text-slate-500"><th className="pb-2">Plan</th><th>Amount</th><th>Status</th></tr></thead>
              <tbody>
                {payments.map((p, i) => (
                  <tr key={i} className="border-t"><td className="py-2">{p.plan}</td><td>₹{p.amount}</td><td>{p.status}</td></tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="text-sm text-slate-400">No payments yet</p>
          )}
        </section>

        <section className="bg-white rounded-2xl border p-6">
          <h2 className="font-semibold text-navy mb-3">LLM — {llm.backend || "LM Studio"}</h2>
          <p className="text-sm text-slate-600">Model: <code>{llm.model}</code></p>
          <p className={`text-sm mt-2 ${llm.available ? "text-emerald-600" : "text-red-600"}`}>
            {llm.message}
          </p>
          <div className="flex gap-2 mt-4">
            <button type="button" disabled={busy} onClick={async () => { setBusy(true); await api.recheckLlm(); load(); setBusy(false); }} className="px-3 py-2 border rounded-lg text-xs font-semibold">Recheck</button>
            <button type="button" disabled={busy} onClick={async () => { setBusy(true); try { const r = await api.testLlm(); setMsg(`Test: ${r.reply}`); } catch (e) { setMsg(e.message); } setBusy(false); }} className="px-3 py-2 bg-navy text-white rounded-lg text-xs font-semibold">Test prompt</button>
          </div>
        </section>

        <section className="bg-white rounded-2xl border p-6 text-sm text-slate-600">
          <h2 className="font-semibold text-navy mb-2">Web & OCR</h2>
          <p>Tavily: {settings?.web_search?.tavily_configured ? "configured" : "not set"}</p>
          <p className="mt-1">OCR: {settings?.ocr?.enabled ? "enabled" : "disabled"}</p>
        </section>
      </div>
    </>
  );
}
