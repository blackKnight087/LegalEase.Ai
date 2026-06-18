"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import * as api from "@/lib/api";

export default function MatterDraftingPanel({ matterId }: { matterId: string }) {
  const router = useRouter();
  const [hub, setHub] = useState<Awaited<ReturnType<typeof api.matterDraftingHub>> | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [packIds, setPackIds] = useState<string[]>([]);

  const load = useCallback(async () => {
    try {
      const h = await api.matterDraftingHub(matterId);
      setHub(h);
      setPackIds((h.documents || []).map((d) => d.draft_id));
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to load drafts");
    }
  }, [matterId]);

  useEffect(() => {
    load();
  }, [load]);

  const createDraft = async (templateId = "") => {
    setBusy(true);
    try {
      const { document } = await api.createMatterDraft(matterId, {
        template_id: templateId,
        document_type: templateId || "custom",
      });
      router.push(`/drafting/${document.draft_id}`);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Create failed");
    } finally {
      setBusy(false);
    }
  };

  const autoBundle = async () => {
    setBusy(true);
    try {
      const r = await api.matterCourtBundle(matterId);
      await load();
      if (r.documents?.length) {
        router.push(`/drafting/${r.documents[0].draft_id}`);
      }
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Bundle failed");
    } finally {
      setBusy(false);
    }
  };

  const downloadPack = async () => {
    if (!packIds.length) return;
    setBusy(true);
    try {
      const { blob, filename } = await api.downloadCourtPackage(matterId, packIds);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Package failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4">
      {err && <p className="text-sm text-red-600">{err}</p>}
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          disabled={busy}
          onClick={() => createDraft()}
          className="px-3 py-2 bg-navy text-white rounded-lg text-sm"
        >
          + Create draft
        </button>
        <button type="button" disabled={busy} onClick={() => createDraft("bail_application")} className="px-3 py-2 border rounded-lg text-sm">
          Bail
        </button>
        <button type="button" disabled={busy} onClick={() => createDraft("agreement")} className="px-3 py-2 border rounded-lg text-sm">
          Agreement
        </button>
        <button type="button" disabled={busy} onClick={() => createDraft("petition")} className="px-3 py-2 border rounded-lg text-sm">
          Petition
        </button>
        <button type="button" disabled={busy} onClick={() => createDraft("affidavit")} className="px-3 py-2 border rounded-lg text-sm">
          Affidavit
        </button>
        <button type="button" disabled={busy} onClick={() => createDraft("nda")} className="px-3 py-2 border rounded-lg text-sm">
          NDA
        </button>
        <button type="button" disabled={busy} onClick={autoBundle} className="px-3 py-2 border rounded-lg text-sm">
          Auto court bundle
        </button>
        <button type="button" disabled={busy || !packIds.length} onClick={downloadPack} className="px-3 py-2 border rounded-lg text-sm">
          Download filing package
        </button>
        <Link href="/drafting" className="px-3 py-2 border rounded-lg text-sm no-underline text-inherit">
          Control center
        </Link>
      </div>

      <div className="grid gap-2">
        <h3 className="text-sm font-semibold text-navy m-0">Matter documents</h3>
        {(hub?.documents || []).length === 0 && (
          <p className="text-sm text-slate-500">No drafts linked to this matter yet.</p>
        )}
        {(hub?.documents || []).map((d) => (
          <label
            key={d.draft_id}
            className="flex items-center gap-3 p-3 border rounded-xl bg-white hover:border-blue-300 cursor-pointer"
          >
            <input
              type="checkbox"
              checked={packIds.includes(d.draft_id)}
              onChange={(e) => {
                setPackIds((ids) =>
                  e.target.checked ? [...ids, d.draft_id] : ids.filter((x) => x !== d.draft_id)
                );
              }}
            />
            <div className="flex-1 min-w-0">
              <Link href={`/drafting/${d.draft_id}`} className="font-medium text-navy underline">
                {d.title}
              </Link>
              <p className="text-xs text-slate-500 m-0">
                {d.status} · v{d.version_count} · filing {d.filing_readiness_score ?? "—"}
              </p>
            </div>
            <Link href={`/drafting/${d.draft_id}/review`} className="text-xs text-navy shrink-0">
              Review
            </Link>
          </label>
        ))}
      </div>

      {(hub?.timeline || []).length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-navy">Document timeline</h3>
          <ul className="text-xs text-slate-600 space-y-1 max-h-40 overflow-y-auto le-scroll">
            {hub!.timeline.map((t, i) => {
              const ev = t as { user_name: string; action: string; title: string; created_at?: string };
              return (
              <li key={i}>
                {ev.user_name} — {ev.action} — {ev.title}{" "}
                <span className="text-slate-400">{ev.created_at ? new Date(ev.created_at).toLocaleString() : ""}</span>
              </li>
            );})}
          </ul>
        </div>
      )}
    </div>
  );
}
