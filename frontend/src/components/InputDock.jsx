import { useRef, useState } from "react";

export default function InputDock({
  value,
  onChange,
  onSubmit,
  disabled,
  attachment,
  onAttach,
  onClearAttach,
  attachOpen,
  setAttachOpen,
  ocrLoading,
}) {
  const fileRef = useRef(null);
  const [dragOver, setDragOver] = useState(false);

  const handleKey = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      onSubmit();
    }
  };

  return (
    <div className="shrink-0 px-6 pb-5 pt-2 bg-canvas">
      <div className="w-full max-w-4xl mx-auto relative">
        {attachOpen && (
          <div className="absolute bottom-full left-0 mb-2 w-72 bg-white rounded-xl border border-slate-200 shadow-xl p-4 z-20">
            <p className="text-xs font-semibold text-slate-600 mb-2">Attach document image (OCR)</p>
            <input
              ref={fileRef}
              type="file"
              accept="image/png,image/jpeg,image/webp"
              className="text-xs w-full"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) onAttach(f);
                e.target.value = "";
              }}
            />
            {attachment && (
              <p className="text-xs text-emerald-600 mt-2 truncate">
                ✓ {attachment.filename} ({attachment.chars?.toLocaleString()} chars)
              </p>
            )}
            <button
              type="button"
              className="mt-2 text-xs text-slate-500 hover:text-navy"
              onClick={onClearAttach}
            >
              Clear attachment
            </button>
          </div>
        )}

        <div
          className={`w-full bg-white/80 backdrop-blur-md border shadow-dock rounded-2xl flex items-end gap-2 px-3 py-2 transition-colors ${
            dragOver ? "border-blue-400" : "border-slate-200"
          }`}
          onDragOver={(e) => {
            e.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragOver(false);
            const f = e.dataTransfer.files?.[0];
            if (f?.type?.startsWith("image/")) onAttach(f);
          }}
        >
          <button
            type="button"
            title="Attach"
            onClick={() => setAttachOpen(!attachOpen)}
            className="shrink-0 w-10 h-10 flex items-center justify-center rounded-xl hover:bg-slate-100 text-lg transition-colors"
          >
            📎
          </button>

          <textarea
            rows={1}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            onKeyDown={handleKey}
            disabled={disabled}
            placeholder="Ask about statutes, precedents, contracts, constitutional law..."
            className="flex-1 resize-none border-0 bg-transparent py-2.5 px-1 text-[0.95rem] text-slate-800 placeholder:text-slate-400 focus:outline-none focus:ring-0 max-h-32 min-h-[44px] font-sans"
          />

          <button
            type="button"
            onClick={onSubmit}
            disabled={disabled || !value.trim()}
            className="shrink-0 w-10 h-10 flex items-center justify-center rounded-xl bg-navy text-white hover:bg-slate-800 disabled:opacity-40 disabled:cursor-not-allowed transition-all hover:scale-105 active:scale-95"
            aria-label="Send"
          >
            {ocrLoading || disabled ? (
              <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            ) : (
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M5 12h14M13 6l6 6-6 6" />
              </svg>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
