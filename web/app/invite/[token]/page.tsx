"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import * as api from "@/lib/api";

export default function OrgInvitePage() {
  const params = useParams();
  const router = useRouter();
  const token = String(params.token || "");
  const [preview, setPreview] = useState<api.OrgInvitePreview | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);

  useEffect(() => {
    if (!token) return;
    api
      .fetchOrgInvitePreview(token)
      .then(setPreview)
      .catch((e) => setErr(e instanceof Error ? e.message : "Invite not found"));
  }, [token]);

  const accept = useCallback(async () => {
    if (!token) return;
    setBusy(true);
    setErr("");
    try {
      const result = await api.acceptOrgInvite(token);
      setDone(true);
      if (result.org_id) {
        setTimeout(() => router.push("/dashboard"), 1200);
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Could not accept invite";
      if (msg.toLowerCase().includes("401") || msg.toLowerCase().includes("not authenticated")) {
        setErr("Please log in with the invited account, then try again.");
      } else {
        setErr(msg);
      }
    } finally {
      setBusy(false);
    }
  }, [token, router]);

  const loginHref = `/login?next=${encodeURIComponent(`/invite/${token}`)}`;

  return (
    <div className="min-h-screen bg-slate-100 flex items-center justify-center p-6">
      <div className="max-w-md w-full bg-white border rounded-2xl shadow-sm p-6 space-y-4">
        <div className="flex items-center gap-2">
          <span className="text-2xl">⚖️</span>
          <div>
            <h1 className="text-lg font-serif font-bold text-navy">Join organization</h1>
            <p className="text-xs text-slate-500">Team invite</p>
          </div>
        </div>

        {err && (
          <p className="text-red-700 text-sm bg-red-50 border border-red-200 rounded-lg px-4 py-3">
            {err}
          </p>
        )}

        {preview && !done && (
          <section className="border rounded-xl p-4 bg-slate-50 space-y-2 text-sm">
            <p>
              You are invited to join <b>{preview.org_name}</b> as{" "}
              <b>{preview.role}</b>.
            </p>
            <p className="text-slate-600">
              Invited email: <span className="font-mono">{preview.email}</span>
            </p>
            <p className="text-slate-500 text-xs">
              Status: {preview.status}
              {preview.expires_at ? ` · expires ${preview.expires_at}` : ""}
            </p>
          </section>
        )}

        {done && (
          <p className="text-green-800 text-sm bg-green-50 border border-green-200 rounded-lg px-4 py-3">
            You joined the organization. Redirecting to dashboard…
          </p>
        )}

        {preview && preview.status === "pending" && !done && (
          <div className="flex flex-col gap-2">
            <button
              type="button"
              onClick={() => void accept()}
              disabled={busy}
              className="w-full py-2.5 rounded-lg bg-navy text-white font-medium disabled:opacity-60"
            >
              {busy ? "Accepting…" : "Accept invite"}
            </button>
            <Link
              href={loginHref}
              className="w-full py-2.5 rounded-lg border text-center text-navy font-medium"
            >
              Log in first
            </Link>
          </div>
        )}

        {preview && preview.status !== "pending" && !done && (
          <p className="text-amber-800 text-sm bg-amber-50 border border-amber-200 rounded-lg px-4 py-3">
            This invite is no longer active ({preview.status}).
          </p>
        )}
      </div>
    </div>
  );
}
