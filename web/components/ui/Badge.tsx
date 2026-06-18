const STYLES = {
  default: "bg-slate-100 text-slate-700",
  brand: "bg-blue-50 text-blue-700",
  success: "bg-emerald-50 text-emerald-700",
  warning: "bg-amber-50 text-amber-800",
  danger: "bg-red-50 text-red-700",
  neutral: "bg-slate-100 text-slate-600",
};

export default function Badge({
  children,
  variant = "default",
  className = "",
}: {
  children: React.ReactNode;
  variant?: keyof typeof STYLES;
  className?: string;
}) {
  return (
    <span
      className={`inline-flex items-center text-[0.65rem] font-bold uppercase tracking-wide px-2 py-0.5 rounded-md ${STYLES[variant]} ${className}`}
    >
      {children}
    </span>
  );
}
