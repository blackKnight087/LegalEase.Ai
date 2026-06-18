"use client";

export default function SuggestionPills({
  items,
  onSelect,
  disabled,
  interactionId,
  mode = "knowledge_base",
}: {
  items: string[];
  onSelect: (text: string) => void;
  disabled?: boolean;
  interactionId?: string;
  mode?: string;
}) {
  if (!items?.length) return null;

  const handleClick = (label: string) => {
    if (interactionId) {
      import("@/lib/api").then(({ learningSignal }) => {
        learningSignal({
          signal: "follow_up_click",
          interaction_id: interactionId,
          metadata: { follow_up: label, mode },
        }).catch(() => {});
      });
    }
    onSelect(label);
  };

  return (
    <div className="shrink-0 max-w-chat mx-auto w-full px-2 sm:px-4 pb-1 sm:pb-2">
      <p className="text-[10px] sm:text-xs text-slate-500 mb-1 sm:mb-2 font-medium hidden sm:block">
        Suggestions
      </p>
      <div className="flex sm:grid sm:grid-cols-3 gap-2 overflow-x-auto touch-scroll-x sm:overflow-visible pb-1 sm:pb-0">
        {items.slice(0, 3).map((label, i) => (
          <button
            key={`${label}-${i}`}
            type="button"
            disabled={disabled}
            onClick={() => handleClick(label)}
            className="shrink-0 sm:shrink rounded-full border border-slate-300 bg-white px-3 py-2.5 sm:py-2 text-xs text-slate-700 hover:border-blue-500 hover:text-blue-800 hover:bg-blue-50 disabled:opacity-50 text-left sm:text-center max-w-[85vw] sm:max-w-none truncate min-h-[40px] sm:min-h-0"
          >
            {label}
          </button>
        ))}
      </div>
    </div>
  );
}
