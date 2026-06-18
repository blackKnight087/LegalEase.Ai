"use client";

import { useMemo, useState } from "react";

type PortalInfo = {
  enabled?: boolean;
  public_url?: string;
  slug?: string;
  submissions_count?: number;
  last_submission_at?: string;
  setup_note?: string;
};

function timeAgo(iso: string) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const diff = Date.now() - d.getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 48) return `${hrs}h ago`;
  return d.toLocaleDateString();
}

export default function IntakePortalCard({
  portal,
  onCopyError,
  compact = false,
}: {
  portal: PortalInfo;
  onCopyError?: (msg: string) => void;
  compact?: boolean;
}) {
  const [copied, setCopied] = useState(false);
  const [showQr, setShowQr] = useState(false);

  const portalUrl = useMemo(() => {
    if (typeof window === "undefined") {
      return String(portal.public_url || "/intake/client");
    }
    const base = window.location.origin;
    const slug = String(portal.slug || "").trim();
    return slug ? `${base}/intake/client?firm=${encodeURIComponent(slug)}` : `${base}/intake/client`;
  }, [portal.public_url, portal.slug]);

  const copyLink = async () => {
    try {
      await navigator.clipboard.writeText(portalUrl);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      onCopyError?.("Could not copy link — select the URL and copy manually.");
    }
  };

  return (
    <section
      className={`le-card rounded-2xl border-2 border-blue-100 bg-gradient-to-br from-white to-blue-50/50 shadow-sm ${
        compact ? "p-4" : "p-5"
      }`}
    >
      <h2 className="text-sm font-semibold text-navy m-0">Client intake portal</h2>
      <p className="text-xs text-slate-600 mt-1 mb-3">
        Share this link so clients submit inquiries without logging in.
      </p>
      <div className="rounded-lg bg-white border border-slate-200 px-3 py-2 font-mono text-[0.7rem] sm:text-xs text-slate-800 break-all">
        {portalUrl}
      </div>
      <div className="flex flex-wrap gap-2 mt-3">
        <button
          type="button"
          onClick={() => void copyLink()}
          className="text-xs px-3 py-2 min-h-[40px] bg-navy text-white rounded-lg hover:opacity-90 transition-opacity"
        >
          {copied ? "Copied!" : "Copy link"}
        </button>
        <a
          href={`mailto:?subject=${encodeURIComponent("Legal consultation inquiry")}&body=${encodeURIComponent(`Please submit your inquiry here:\n${portalUrl}`)}`}
          className="text-xs px-3 py-2 min-h-[40px] inline-flex items-center border rounded-lg hover:bg-white"
        >
          Email
        </a>
        <a
          href={`https://wa.me/?text=${encodeURIComponent(`Submit your legal inquiry: ${portalUrl}`)}`}
          target="_blank"
          rel="noreferrer"
          className="text-xs px-3 py-2 min-h-[40px] inline-flex items-center border rounded-lg hover:bg-white"
        >
          WhatsApp
        </a>
        <button
          type="button"
          onClick={() => setShowQr((v) => !v)}
          className="text-xs px-3 py-2 min-h-[40px] border rounded-lg hover:bg-white"
        >
          {showQr ? "Hide QR" : "QR code"}
        </button>
        <a
          href={portalUrl}
          target="_blank"
          rel="noreferrer"
          className="text-xs px-3 py-2 min-h-[40px] inline-flex items-center text-blue-700 hover:underline"
        >
          Preview →
        </a>
      </div>
      {showQr ? (
        <img
          src={`https://api.qrserver.com/v1/create-qr-code/?size=140x140&data=${encodeURIComponent(portalUrl)}`}
          alt="Intake portal QR code"
          className="mt-3 mx-auto border rounded-lg"
          width={140}
          height={140}
          loading="lazy"
        />
      ) : null}
      <p className="text-[0.65rem] text-slate-500 mt-3 m-0">
        Submissions: {String(portal.submissions_count ?? 0)}
        {portal.last_submission_at ? ` · Last: ${timeAgo(String(portal.last_submission_at))}` : ""}
      </p>
      {!portal.enabled ? (
        <p className="text-[0.65rem] text-amber-800 bg-amber-50 border border-amber-100 rounded-lg px-2 py-1.5 mt-2 m-0">
          {String(
            portal.setup_note ||
              "Enable INTAKE_PUBLIC_ENABLED=1 and INTAKE_ORG_USER_ID in server .env for live submissions."
          )}
        </p>
      ) : null}
    </section>
  );
}
