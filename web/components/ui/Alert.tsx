import { ReactNode } from "react";

const STYLES = {
  error: "bg-red-50 border-red-200/80 text-red-800",
  success: "bg-emerald-50 border-emerald-200/80 text-emerald-900",
  warning: "bg-amber-50 border-amber-200/80 text-amber-900",
  info: "bg-blue-50 border-blue-200/80 text-blue-900",
};

export default function Alert({
  variant = "error",
  children,
  className = "",
}: {
  variant?: keyof typeof STYLES;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={`text-sm border rounded-xl px-4 py-3 leading-relaxed ${STYLES[variant]} ${className}`}
      role="alert"
    >
      {children}
    </div>
  );
}
