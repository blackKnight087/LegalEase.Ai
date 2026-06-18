"use client";

import { useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import * as api from "@/lib/api";

export default function ClientPortalPage() {
  const params = useParams();
  const token = String(params.token || "");
  const [data, setData] = useState<Record<string, unknown> | null>(null);
  const [err, setErr] = useState("");
  const [uploadMsg, setUploadMsg] = useState("");
  const [uploadBusy, setUploadBusy] = useState(false);
  const [signBusy, setSignBusy] = useState(false);
  const [signMsg, setSignMsg] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  const reload = () => {
    if (!token) return;
    api
      .fetchPortalView(token)
      .then(setData)
      .catch((e) => setErr(e instanceof Error ? e.message : "Link invalid"));
  };

  useEffect(() => {
    reload();
  }, [token]);

  const onUpload = async (file: File) => {
    setUploadBusy(true);
    setUploadMsg("");
    try {
      await api.uploadPortalDocument(token, file);
      setUploadMsg(`Uploaded ${file.name}. Your lawyer has been notified.`);
      reload();
    } catch (e) {
      setUploadMsg(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setUploadBusy(false);
    }
  };

  const matter = (data?.matter as Record<string, unknown>) || {};
  const trust = (data?.trust_summary as Record<string, number>) || {};
  const notes = (data?.recent_notes as Array<Record<string, string>>) || [];

  return (
    <div className="min-h-screen bg-slate-100 p-6">
      <div className="max-w-xl mx-auto bg-white border rounded-2xl shadow-sm p-6 space-y-4">
        <div className="flex items-center gap-2">
          <span className="text-2xl">⚖️</span>
          <div>
            <h1 className="text-lg font-serif font-bold text-navy">Client Portal</h1>
            <p className="text-xs text-slate-500">Case status & document upload</p>
          </div>
        </div>
        {err && (
          <p className="text-red-700 text-sm bg-red-50 border border-red-200 rounded-lg px-4 py-3">
            {err}
          </p>
        )}
        {uploadMsg && (
          <p className="text-sm bg-slate-50 border rounded-lg px-4 py-3">{uploadMsg}</p>
        )}
        {data && (
          <>
            <section className="border rounded-xl p-4 bg-slate-50">
              <h2 className="font-semibold text-navy">{String(matter.matter_name || "Matter")}</h2>
              <p className="text-sm text-slate-600 mt-1">
                {String(matter.practice_area || "")}
                {matter.case_number ? ` · ${matter.case_number}` : ""}
              </p>
              <p className="text-sm mt-2">
                Status: <b>{String(matter.status_tier || "ACTIVE")}</b>
                {matter.venue ? ` · ${matter.venue}` : ""}
              </p>
            </section>
            <section className="grid grid-cols-2 gap-3 text-sm">
              <div className="p-3 border rounded-lg bg-amber-50">
                <b>Trust (INR)</b>
                <p className="text-lg">₹{(trust.trust_balance_inr || 0).toLocaleString("en-IN")}</p>
              </div>
              <div className="p-3 border rounded-lg">
                <b>Operating (INR)</b>
                <p className="text-lg">
                  ₹{(trust.operating_balance_inr || 0).toLocaleString("en-IN")}
                </p>
              </div>
            </section>
            <section className="border rounded-xl p-4 bg-emerald-50/50">
              <h3 className="text-sm font-semibold text-navy mb-2">Acknowledge & sign</h3>
              <p className="text-xs text-slate-500 mb-3">
                Records your intent to acknowledge case status (e-sign stub until DocuSign is configured).
              </p>
              {signMsg && (
                <p className="text-sm mb-2 text-slate-700">{signMsg}</p>
              )}
              <button
                type="button"
                disabled={signBusy}
                onClick={async () => {
                  setSignBusy(true);
                  setSignMsg("");
                  try {
                    const out = await api.signPortalDocument(token, {
                      intent: "acknowledge",
                    });
                    setSignMsg(
                      String(out.note || "Signature recorded. Your lawyer has been notified.")
                    );
                  } catch (e) {
                    setSignMsg(e instanceof Error ? e.message : "Sign failed");
                  } finally {
                    setSignBusy(false);
                  }
                }}
                className="px-4 py-2 border border-navy text-navy rounded-lg text-sm disabled:opacity-50"
              >
                {signBusy ? "Recording…" : "I acknowledge"}
              </button>
            </section>
            <section className="border rounded-xl p-4">
              <h3 className="text-sm font-semibold text-navy mb-2">Upload a document</h3>
              <p className="text-xs text-slate-500 mb-3">
                PDF or image up to 25 MB. Your lawyer will review uploads.
              </p>
              <input
                ref={fileRef}
                type="file"
                className="hidden"
                accept=".pdf,.png,.jpg,.jpeg,.webp,.doc,.docx"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) void onUpload(f);
                  e.target.value = "";
                }}
              />
              <button
                type="button"
                disabled={uploadBusy}
                onClick={() => fileRef.current?.click()}
                className="px-4 py-2 bg-navy text-white rounded-lg text-sm disabled:opacity-50"
              >
                {uploadBusy ? "Uploading…" : "Choose file"}
              </button>
            </section>
            {notes.length > 0 && (
              <section>
                <h3 className="text-sm font-semibold text-navy mb-2">Recent updates</h3>
                <ul className="space-y-2 text-sm">
                  {notes.map((n, i) => (
                    <li key={i} className="p-2 bg-slate-50 border rounded-lg">
                      {n.content}
                      <span className="block text-xs text-slate-500 mt-1">{n.timestamp}</span>
                    </li>
                  ))}
                </ul>
              </section>
            )}
            <p className="text-xs text-slate-500">{String(data.disclaimer || "")}</p>
          </>
        )}
      </div>
    </div>
  );
}
