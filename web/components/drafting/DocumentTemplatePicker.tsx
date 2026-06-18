"use client";

import DraftingTemplateGallery from "@/components/drafting/DraftingTemplateGallery";
import { type LegalTemplateId } from "@/lib/legalDocumentTemplates";

type Props = {
  open: boolean;
  onClose: () => void;
  onApply: (id: LegalTemplateId, replace: boolean) => void;
  documentType?: string;
};

export default function DocumentTemplatePicker({ open, onClose, onApply, documentType }: Props) {
  if (!open) return null;

  const suggested = documentType?.toLowerCase().replace(/\s+/g, "_");

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6"
      style={{ background: "rgba(15, 23, 42, 0.55)" }}
      role="dialog"
      aria-modal="true"
    >
      <div className="bg-white rounded-2xl shadow-2xl max-w-4xl w-full max-h-[92vh] flex flex-col overflow-hidden border border-slate-200/80">
        <div className="px-6 py-5 border-b border-slate-200 bg-gradient-to-r from-slate-900 to-slate-800 text-white shrink-0">
          <div className="flex justify-between items-start gap-4">
            <div>
              <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400 m-0">Drafting Studio</p>
              <h2 className="font-serif text-xl font-bold m-0 mt-1">Document templates</h2>
              <p className="text-sm text-slate-300 m-0 mt-1.5 max-w-lg">
                Replace or rebuild with a firm-standard structure. Matter variables apply when linked.
              </p>
            </div>
            <button
              type="button"
              onClick={onClose}
              className="text-slate-300 hover:text-white text-2xl leading-none w-10 h-10 rounded-lg hover:bg-white/10"
              aria-label="Close"
            >
              ×
            </button>
          </div>
        </div>
        <div className="flex-1 overflow-y-auto le-scroll p-6 bg-slate-50/50">
          <DraftingTemplateGallery
            compact
            highlightId={suggested}
            onSelect={(id) => {
              onApply(id, true);
              onClose();
            }}
          />
        </div>
        <div className="px-6 py-4 border-t border-slate-200 bg-white flex justify-end gap-2 shrink-0">
          <button
            type="button"
            className="text-sm px-4 py-2.5 rounded-xl border border-slate-200 text-slate-700 font-medium hover:bg-slate-50"
            onClick={onClose}
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}
