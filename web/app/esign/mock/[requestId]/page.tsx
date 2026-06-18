"use client";

import { useState } from "react";
import { useParams, useSearchParams } from "next/navigation";
import { getApiBase } from "@/lib/api";

export default function MockEsignPage() {
  const params = useParams();
  const search = useSearchParams();
  const requestId = String(params.requestId || "");
  const email = search.get("email") || "";
  const [done, setDone] = useState(false);
  const [err, setErr] = useState("");

  const sign = async () => {
    setErr("");
    try {
      const res = await fetch(
        `${getApiBase()}/api/v1/esign/mock/${encodeURIComponent(requestId)}/complete`,
        { method: "POST" }
      );
      if (!res.ok) throw new Error("Could not complete signature");
      setDone(true);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed");
    }
  };

  return (
    <div className="min-h-screen bg-slate-100 flex items-center justify-center p-6">
      <div className="max-w-md w-full bg-white border rounded-2xl p-6 text-center space-y-4">
        <h1 className="text-lg font-bold text-navy">Mock E-Signature</h1>
        <p className="text-sm text-slate-600">Signer: {email || "—"}</p>
        {done ? (
          <p className="text-emerald-700 font-medium">Document marked as signed.</p>
        ) : (
          <button
            type="button"
            onClick={sign}
            className="px-6 py-2 bg-navy text-white rounded-lg text-sm"
          >
            Sign document (dev)
          </button>
        )}
        {err && <p className="text-red-600 text-sm">{err}</p>}
      </div>
    </div>
  );
}
