"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import * as api from "@/lib/api";

export default function DraftLitigationPanel({
  draftId,
  matterId,
}: {
  draftId: string;
  matterId: string;
}) {
  const [hearings, setHearings] = useState<Array<Record<string, unknown>>>([]);
  const [links, setLinks] = useState<Array<Record<string, unknown>>>([]);
  const [hearingId, setHearingId] = useState("");
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!matterId) return;
    api.listMatterHearings(matterId).then((r) => setHearings(r.hearings || [])).catch(() => {});
    api.listDraftLinks(draftId).then((r) => setLinks(r.links || [])).catch(() => {});
  }, [matterId, draftId]);

  if (!matterId) {
    return (
      <p className="text-xs text-amber-700">Link a matter to sync with Litigation and Billing.</p>
    );
  }

  return (
    <div className="text-xs space-y-2">
      <p className="font-medium text-navy m-0">Platform links</p>
      <div className="flex flex-wrap gap-1">
        <Link href={`/litigation?tab=hearings&matter=${matterId}`} className="underline text-navy">
          Hearings
        </Link>
        <span>·</span>
        <Link href={`/litigation?tab=orders&matter=${matterId}`} className="underline text-navy">
          Orders
        </Link>
        <span>·</span>
        <Link href={`/billing?matter=${matterId}`} className="underline text-navy">
          Billing
        </Link>
      </div>
      <select
        className="w-full border rounded px-2 py-1"
        value={hearingId}
        onChange={(e) => setHearingId(e.target.value)}
      >
        <option value="">Link to hearing…</option>
        {hearings.map((h) => (
          <option key={String(h.hearing_id)} value={String(h.hearing_id)}>
            {String(h.hearing_date)} — {String(h.court_name || h.purpose || "Hearing")}
          </option>
        ))}
      </select>
      <button
        type="button"
        disabled={!hearingId || busy}
        className="w-full py-1 border rounded-lg"
        onClick={async () => {
          setBusy(true);
          setErr("");
          try {
            await api.linkDraftToHearing(draftId, hearingId);
            setMsg("Linked to hearing");
            const r = await api.listDraftLinks(draftId);
            setLinks(r.links || []);
          } catch (e) {
            setErr(e instanceof Error ? e.message : "Link failed");
          } finally {
            setBusy(false);
          }
        }}
      >
        Link to hearing
      </button>
      <button
        type="button"
        disabled={busy}
        className="w-full py-1 bg-navy text-white rounded-lg"
        onClick={async () => {
          setBusy(true);
          try {
            const r = await api.syncDraftToLitigation(draftId);
            setMsg(`Synced — order ${String((r as { order_id?: string }).order_id || "")}`);
          } catch (e) {
            setErr(e instanceof Error ? e.message : "Sync failed");
          } finally {
            setBusy(false);
          }
        }}
      >
        Sync to court orders (filed)
      </button>
      {msg && <p className="text-green-700 m-0">{msg}</p>}
      {err && <p className="text-red-600 m-0">{err}</p>}
      {links.length > 0 && (
        <ul className="m-0 pl-4">
          {links.map((l) => (
            <li key={String(l.link_id)}>
              {String(l.link_type)} → {String(l.target_id).slice(0, 8)}…
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
