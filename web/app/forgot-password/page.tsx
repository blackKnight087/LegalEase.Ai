"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import * as api from "@/lib/api";
import { backendStartHint, isLocalDevHost } from "@/lib/runtimeEnv";

export default function ForgotPasswordPage() {
  const [username, setUsername] = useState("");
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setErr("");
    setMsg("");
    try {
      await api.requestPasswordReset(username.trim());
      setMsg("If that account has an email on file, a reset link was sent. Check spam. No email? See backend logs for a dev reset link.");
    } catch (ex) {
      const msg = ex instanceof Error ? ex.message : "Request failed";
      if (/internal server error|failed to fetch|502|503|504/i.test(msg)) {
        setErr(
          isLocalDevHost()
            ? `Backend is not running. ${backendStartHint()}`
            : "Server unavailable — try again in a moment."
        );
      } else {
        setErr(msg);
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-100 flex items-center justify-center p-6">
      <div className="max-w-md w-full bg-white border rounded-2xl p-6 space-y-4">
        <h1 className="text-lg font-serif font-bold text-navy">Forgot password</h1>
        <p className="text-sm text-slate-600">
          Enter the <strong>email address</strong> on your account (or your username if you registered with an email as username).
        </p>
        {msg && (
          <p className="text-sm text-green-800 bg-green-50 border border-green-200 rounded-lg px-4 py-3">
            {msg}
          </p>
        )}
        {err && (
          <p className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-4 py-3">
            {err}
          </p>
        )}
        <form onSubmit={onSubmit} className="space-y-3">
          <label className="text-sm font-medium">Email or username</label>
          <input
            className="w-full border rounded-lg px-3 py-2 text-sm"
            type="email"
            autoComplete="email"
            placeholder="you@gmail.com"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            required
          />
          <button
            type="submit"
            disabled={busy}
            className="w-full py-2.5 rounded-lg bg-navy text-white font-medium disabled:opacity-60"
          >
            {busy ? "Sending…" : "Send reset link"}
          </button>
        </form>
        <Link href="/login" className="text-sm text-blue-700 hover:underline">
          Back to login
        </Link>
      </div>
    </div>
  );
}
