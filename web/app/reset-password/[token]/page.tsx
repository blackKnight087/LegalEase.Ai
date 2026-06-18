"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import * as api from "@/lib/api";

export default function ResetPasswordPage() {
  const params = useParams();
  const router = useRouter();
  const token = String(params.token || "");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setErr("");
    try {
      await api.resetPassword(token, password, confirm);
      router.push("/login");
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : "Reset failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-100 flex items-center justify-center p-6">
      <div className="max-w-md w-full bg-white border rounded-2xl p-6 space-y-4">
        <h1 className="text-lg font-serif font-bold text-navy">Set new password</h1>
        {err && (
          <p className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-4 py-3">
            {err}
          </p>
        )}
        <form onSubmit={onSubmit} className="space-y-3">
          <label className="text-sm font-medium">New password</label>
          <input
            type="password"
            className="w-full border rounded-lg px-3 py-2 text-sm"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={6}
          />
          <label className="text-sm font-medium">Confirm password</label>
          <input
            type="password"
            className="w-full border rounded-lg px-3 py-2 text-sm"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            required
            minLength={6}
          />
          <button
            type="submit"
            disabled={busy || !token}
            className="w-full py-2.5 rounded-lg bg-navy text-white font-medium disabled:opacity-60"
          >
            {busy ? "Saving…" : "Update password"}
          </button>
        </form>
        <Link href="/login" className="text-sm text-blue-700 hover:underline">
          Back to login
        </Link>
      </div>
    </div>
  );
}
