"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import PageHeader from "@/components/ui/PageHeader";
import MatterDeleteButton from "@/components/matters/MatterDeleteButton";
import * as api from "@/lib/api";

export default function MattersPage() {
  const router = useRouter();
  const [matters, setMatters] = useState<
    Array<api.Matter & { document_count?: number; kb_ready?: boolean }>
  >([]);
  const [err, setErr] = useState("");

  const load = useCallback(async () => {
    setErr("");
    try {
      const r = await api.listMattersSummary();
      setMatters(r.matters || []);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to load");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="flex flex-col h-full min-h-0">
      <PageHeader
        title="Matters"
        subtitle="Isolated case workspaces — each matter has its own documents, KB, timeline, and AI memory"
      />
      <div className="flex-1 overflow-y-auto overflow-x-hidden le-scroll le-page-body max-w-5xl mx-auto w-full space-y-4 sm:space-y-6">
        {err && (
          <p className="text-red-600 text-sm bg-red-50 border border-red-200 rounded-lg px-4 py-3">
            {err}
          </p>
        )}

        <div className="flex flex-wrap justify-between items-center gap-3">
          <p className="text-sm text-slate-600 m-0">
            {matters.length} matter{matters.length === 1 ? "" : "s"}
          </p>
          <div className="flex flex-wrap gap-2">
            <Link
              href="/litigation?tab=evidence"
              className="rounded-lg border border-navy text-navy px-4 py-2 text-sm font-semibold hover:bg-slate-50"
            >
              Evidence Desk
            </Link>
            <Link
              href="/matters/new"
              className="rounded-lg bg-navy text-white px-4 py-2 text-sm font-semibold hover:bg-slate-800"
            >
              + New matter
            </Link>
          </div>
        </div>

        <div className="grid gap-3">
          {matters.map((m) => (
            <div
              key={m.matter_id}
              className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm hover:border-navy/40 hover:shadow-md transition-all"
            >
              <div className="flex flex-wrap justify-between gap-2">
                <Link href={`/matters/${m.matter_id}`} className="flex-1 min-w-0">
                  <h2 className="text-base font-semibold text-navy m-0">{m.matter_name}</h2>
                  <p className="text-xs text-slate-600 mt-1">
                    {m.matter_type || m.practice_area} · {m.status_tier || "Open"}
                    {m.client_name ? ` · ${m.client_name}` : ""}
                  </p>
                  {m.venue && (
                    <p className="text-xs text-slate-500 m-0 mt-0.5">{m.venue}</p>
                  )}
                </Link>
                <div className="flex flex-col items-end gap-2 text-xs">
                  <span
                    className={`inline-block px-2 py-0.5 rounded-full font-medium ${
                      m.kb_ready
                        ? "bg-emerald-50 text-emerald-800"
                        : "bg-amber-50 text-amber-800"
                    }`}
                  >
                    {m.kb_ready ? "KB ready" : "KB pending"}
                  </span>
                  <p className="text-slate-500 m-0">{m.document_count ?? 0} documents</p>
                  <MatterDeleteButton
                    matterId={m.matter_id}
                    matterName={m.matter_name || ""}
                    label="Delete"
                    className="px-2 py-1 text-xs font-medium text-red-700 border border-red-300 rounded hover:bg-red-50"
                    onDeleted={() => {
                      setMatters((prev) => prev.filter((x) => x.matter_id !== m.matter_id));
                      if (typeof window !== "undefined") {
                        const active = localStorage.getItem("legalease_active_matter");
                        if (active === m.matter_id) {
                          localStorage.removeItem("legalease_active_matter");
                        }
                      }
                      router.refresh();
                    }}
                  />
                </div>
              </div>
            </div>
          ))}
          {!matters.length && (
            <p className="text-sm text-slate-500 text-center py-12">
              No matters yet.{" "}
              <Link href="/matters/new" className="text-blue-700 font-medium">
                Create your first case workspace
              </Link>
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
