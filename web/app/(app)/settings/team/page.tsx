"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import PageHeader from "@/components/ui/PageHeader";
import * as api from "@/lib/api";

export default function TeamSettingsPage() {
  const [org, setOrg] = useState<Record<string, unknown> | null>(null);
  const [members, setMembers] = useState<Array<Record<string, unknown>>>([]);
  const [invites, setInvites] = useState<Array<Record<string, unknown>>>([]);
  const [email, setEmail] = useState("");
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const [branding, setBranding] = useState<api.OrgBranding | null>(null);
  const [logoUrl, setLogoUrl] = useState("");
  const [primaryColor, setPrimaryColor] = useState("#1e3a5f");
  const [customDomain, setCustomDomain] = useState("");
  const [supportEmail, setSupportEmail] = useState("");

  const load = useCallback(() => {
    setErr("");
    api
      .fetchMyOrg()
      .then((d) => {
        setOrg((d.org as Record<string, unknown>) || null);
        setMembers((d.members as Array<Record<string, unknown>>) || []);
        const oid = String((d.org as Record<string, unknown>)?.org_id || "");
        if (oid) {
          api.fetchEnterpriseBranding().then((b) => {
            const br = b.branding || {};
            setBranding(br);
            setLogoUrl(br.logo_url || "");
            setPrimaryColor(br.primary_color || "#1e3a5f");
            setCustomDomain(br.custom_domain || "");
            setSupportEmail(br.support_email || "");
          }).catch(() => {});
        }
      })
      .catch((e) => setErr(e instanceof Error ? e.message : "Failed to load org"));
    api
      .fetchOrgInvites()
      .then((d) => setInvites(d.invites || []))
      .catch(() => setInvites([]));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const invite = async () => {
    setBusy(true);
    setMsg("");
    try {
      const r = await api.inviteOrgMember(email.trim());
      const inv = (r.invite || {}) as Record<string, string>;
      setMsg(inv.invite_url ? `Invite sent: ${inv.invite_url}` : "Invite created.");
      setEmail("");
      load();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "Invite failed");
    } finally {
      setBusy(false);
    }
  };

  const saveBranding = async () => {
    const orgId = String(org?.org_id || branding?.org_id || "");
    if (!orgId) return;
    setBusy(true);
    setMsg("");
    try {
      await api.patchOrgBranding(orgId, {
        logo_url: logoUrl,
        primary_color: primaryColor,
        custom_domain: customDomain,
        support_email: supportEmail,
      });
      setMsg("Branding saved.");
      load();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "Save failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-col h-full min-h-0">
      <PageHeader title="Team" subtitle="Organization members and invites">
        <Link href="/settings" className="text-sm text-blue-700 hover:underline">
          ← Settings
        </Link>
      </PageHeader>
      <div className="flex-1 overflow-y-auto overflow-x-hidden le-scroll le-page-body max-w-2xl mx-auto w-full space-y-4 sm:space-y-6">
        {err && (
          <p className="text-sm text-red-600 bg-red-50 border rounded-lg px-4 py-3">{err}</p>
        )}
        {msg && (
          <p className="text-sm text-slate-700 bg-slate-50 border rounded-lg px-4 py-3 break-all">
            {msg}
          </p>
        )}
        {org && (
          <section className="bg-white border rounded-2xl p-6">
            <h2 className="font-semibold text-navy">{String(org.name)}</h2>
            <p className="text-sm text-slate-600 mt-1">
              Plan: {String(org.plan)} · Seats: {String(members.length)} /{" "}
              {String(org.seat_limit)}
            </p>
          </section>
        )}
        <section className="bg-white border rounded-2xl p-6 space-y-3">
          <h3 className="font-semibold text-navy">White-label branding</h3>
          <p className="text-sm text-slate-600">Enterprise firms can customize portal and client-facing colors.</p>
          <label className="block text-sm">
            Logo URL
            <input
              className="mt-1 w-full border rounded-lg px-3 py-2 text-sm"
              value={logoUrl}
              onChange={(e) => setLogoUrl(e.target.value)}
              placeholder="https://…"
            />
          </label>
          <label className="block text-sm">
            Primary color
            <input
              type="color"
              className="mt-1 h-10 w-20 border rounded"
              value={primaryColor}
              onChange={(e) => setPrimaryColor(e.target.value)}
            />
          </label>
          <label className="block text-sm">
            Custom domain
            <input
              className="mt-1 w-full border rounded-lg px-3 py-2 text-sm"
              value={customDomain}
              onChange={(e) => setCustomDomain(e.target.value)}
              placeholder="legal.yourfirm.com"
            />
          </label>
          <label className="block text-sm">
            Support email
            <input
              className="mt-1 w-full border rounded-lg px-3 py-2 text-sm"
              value={supportEmail}
              onChange={(e) => setSupportEmail(e.target.value)}
              placeholder="support@firm.com"
            />
          </label>
          <button
            type="button"
            disabled={busy}
            onClick={() => void saveBranding()}
            className="px-4 py-2 bg-navy text-white rounded-lg text-sm disabled:opacity-50"
          >
            Save branding
          </button>
        </section>
        <section className="bg-white border rounded-2xl p-6">
          <h3 className="font-semibold text-navy mb-3">Members</h3>
          <ul className="space-y-2 text-sm">
            {members.map((m) => (
              <li key={String(m.user_id)} className="flex justify-between border-b py-2">
                <span>{String(m.username || m.user_id)}</span>
                <span className="text-slate-500">{String(m.role)}</span>
              </li>
            ))}
          </ul>
        </section>
        <section className="bg-white border rounded-2xl p-6 space-y-3">
          <h3 className="font-semibold text-navy">Invite teammate</h3>
          <input
            className="w-full border rounded-lg px-3 py-2 text-sm"
            placeholder="email@firm.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
          <button
            type="button"
            disabled={busy || !email.trim()}
            onClick={() => void invite()}
            className="px-4 py-2 bg-navy text-white rounded-lg text-sm font-medium disabled:opacity-50"
          >
            Send invite
          </button>
        </section>
        {invites.length > 0 && (
          <section className="bg-white border rounded-2xl p-6">
            <h3 className="font-semibold text-navy mb-2">Pending invites</h3>
            <ul className="text-sm space-y-2">
              {invites.map((i) => (
                <li key={String(i.invite_id)} className="flex justify-between">
                  <span>{String(i.email)}</span>
                  <span className="text-slate-500">{String(i.role)}</span>
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>
    </div>
  );
}
