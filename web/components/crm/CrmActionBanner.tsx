"use client";

type Props = {
  message: string;
  variant: "success" | "error";
  onDismiss?: () => void;
};

export default function CrmActionBanner({ message, variant, onDismiss }: Props) {
  if (!message) return null;
  const styles =
    variant === "success"
      ? "bg-emerald-50 border-emerald-200 text-emerald-900"
      : "bg-red-50 border-red-200 text-red-800";

  return (
    <div className={`flex items-start gap-2 text-sm border rounded-lg px-3 py-2 mb-2 ${styles}`}>
      <p className="flex-1">{message}</p>
      {onDismiss ? (
        <button type="button" onClick={onDismiss} className="text-xs font-bold opacity-70 hover:opacity-100">
          Dismiss
        </button>
      ) : null}
    </div>
  );
}
