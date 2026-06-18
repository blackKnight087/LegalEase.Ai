export default function SuggestionPills({ items, onPick, disabled }) {
  if (!items?.length) return null;
  return (
    <div className="shrink-0 flex flex-wrap gap-2 px-8 pb-2">
      {items.map((label) => (
        <button
          key={label}
          type="button"
          disabled={disabled}
          onClick={() => onPick(label)}
          className="px-3 py-1.5 text-xs font-medium bg-white border border-slate-200 rounded-lg hover:border-navy hover:text-navy transition-colors disabled:opacity-50"
        >
          {label}
        </button>
      ))}
    </div>
  );
}
