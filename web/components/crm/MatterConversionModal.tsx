"use client";

type Props = {
  preview: Record<string, unknown> | null;
  open: boolean;
  onClose: () => void;
  onConfirm: () => void;
  busy: boolean;
};

export default function MatterConversionModal({
  preview,
  open,
  onClose,
  onConfirm,
  busy,
}: Props) {
  if (!open || !preview) return null;
  const mp = (preview.matter_preview || {}) as Record<string, unknown>;
  const tasks = (mp.tasks as Array<Record<string, unknown>>) || [];
  const deadlines = (mp.deadlines as Array<Record<string, unknown>>) || [];
  const entities = (preview.entities as Array<Record<string, unknown>>) || [];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="bg-white rounded-xl max-w-lg w-full max-h-[90vh] overflow-y-auto p-6 shadow-xl">
        <h2 className="text-lg font-semibold text-navy mb-2">Convert to matter</h2>
        <p className="text-sm text-slate-600 mb-4">
          Review what will be created in the matter workspace.
        </p>
        <p className="text-sm font-medium">{String(mp.suggested_name || "New matter")}</p>
        <p className="text-xs text-slate-500 mb-4">{String(mp.practice_area || "")}</p>
        {!!tasks.length && (
          <div className="mb-3">
            <p className="text-xs font-semibold uppercase text-slate-500">Tasks</p>
            <ul className="text-sm list-disc pl-4">
              {tasks.map((t, i) => (
                <li key={i}>{String(t.title)}</li>
              ))}
            </ul>
          </div>
        )}
        {!!deadlines.length && (
          <div className="mb-3">
            <p className="text-xs font-semibold uppercase text-slate-500">Deadlines</p>
            <ul className="text-sm list-disc pl-4">
              {deadlines.map((d, i) => (
                <li key={i}>{String(d.title)}</li>
              ))}
            </ul>
          </div>
        )}
        {!!entities.length && (
          <div className="mb-3">
            <p className="text-xs font-semibold uppercase text-slate-500">Entities</p>
            <ul className="text-sm list-disc pl-4">
              {entities.map((e, i) => (
                <li key={i}>
                  {String(e.label)} ({String(e.entity_type || e.type)})
                </li>
              ))}
            </ul>
          </div>
        )}
        <div className="flex gap-2 mt-6">
          <button
            type="button"
            onClick={onClose}
            className="flex-1 px-4 py-2 border rounded-lg text-sm"
          >
            Cancel
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={onConfirm}
            className="flex-1 px-4 py-2 bg-emerald-700 text-white rounded-lg text-sm disabled:opacity-50"
          >
            {busy ? "Converting…" : "Create matter"}
          </button>
        </div>
      </div>
    </div>
  );
}
