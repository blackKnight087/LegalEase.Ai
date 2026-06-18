"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";

const API = "/api/v1";

function VerifyEmailInner() {
  const params = useSearchParams();
  const token = params.get("token") || "";
  const [status, setStatus] = useState<"idle" | "ok" | "error">("idle");
  const [message, setMessage] = useState("");

  useEffect(() => {
    if (!token) {
      setStatus("error");
      setMessage("Missing verification token.");
      return;
    }
    fetch(`${API}/account/verify-email/confirm`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token }),
    })
      .then(async (r) => {
        const data = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(data.detail || "Verification failed");
        setStatus("ok");
        setMessage("Your email is verified. You can sign in and continue setup.");
      })
      .catch((e: Error) => {
        setStatus("error");
        setMessage(e.message || "Verification failed");
      });
  }, [token]);

  return (
    <main className="min-h-screen flex items-center justify-center p-6 bg-slate-950 text-slate-100">
      <div className="max-w-md w-full rounded-xl border border-slate-700 bg-slate-900 p-8 text-center">
        <h1 className="text-xl font-semibold mb-4">Email verification</h1>
        {status === "idle" && <p className="text-slate-400">Verifying…</p>}
        {status === "ok" && <p className="text-emerald-400">{message}</p>}
        {status === "error" && <p className="text-red-400">{message}</p>}
        <Link href="/login" className="inline-block mt-6 text-blue-400 hover:underline">
          Back to login
        </Link>
      </div>
    </main>
  );
}

export default function VerifyEmailPage() {
  return (
    <Suspense
      fallback={
        <main className="min-h-screen flex items-center justify-center p-6 bg-slate-950 text-slate-100">
          <p className="text-slate-400">Loading…</p>
        </main>
      }
    >
      <VerifyEmailInner />
    </Suspense>
  );
}
