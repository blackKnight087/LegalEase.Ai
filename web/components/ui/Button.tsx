"use client";

import Link from "next/link";
import { ButtonHTMLAttributes, forwardRef } from "react";

type Variant = "primary" | "secondary" | "ghost" | "danger" | "outline";
type Size = "sm" | "md" | "lg";

const VARIANT: Record<Variant, string> = {
  primary:
    "bg-[var(--le-brand)] text-white shadow-sm hover:bg-[var(--le-brand-hover)] border border-transparent",
  secondary:
    "bg-white text-slate-700 border border-slate-200 shadow-sm hover:bg-slate-50 hover:border-slate-300",
  ghost: "bg-transparent text-slate-600 hover:bg-slate-100 border border-transparent",
  danger:
    "bg-red-600 text-white hover:bg-red-700 border border-transparent shadow-sm",
  outline:
    "bg-transparent text-[var(--le-brand)] border border-[var(--le-brand)]/30 hover:bg-blue-50",
};

const SIZE: Record<Size, string> = {
  sm: "text-xs px-3 py-2 min-h-[36px] rounded-lg gap-1.5",
  md: "text-sm px-4 py-2.5 min-h-[40px] rounded-xl gap-2",
  lg: "text-sm px-5 py-3 min-h-[44px] rounded-xl gap-2",
};

type BaseProps = {
  variant?: Variant;
  size?: Size;
  className?: string;
  loading?: boolean;
};

type ButtonProps = BaseProps &
  ButtonHTMLAttributes<HTMLButtonElement> & { href?: undefined };

type LinkProps = BaseProps & {
  href: string;
  children: React.ReactNode;
};

function classes(variant: Variant, size: Size, className?: string, disabled?: boolean) {
  return [
    "le-interactive inline-flex items-center justify-center font-semibold",
    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500/40 focus-visible:ring-offset-2",
    "disabled:opacity-50 disabled:pointer-events-none",
    VARIANT[variant],
    SIZE[size],
    className,
  ]
    .filter(Boolean)
    .join(" ");
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "primary", size = "md", className, loading, disabled, children, ...rest },
  ref
) {
  return (
    <button
      ref={ref}
      type="button"
      disabled={disabled || loading}
      className={classes(variant, size, className, disabled)}
      {...rest}
    >
      {loading && (
        <span className="w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin shrink-0" />
      )}
      {children}
    </button>
  );
});

export function ButtonLink({
  href,
  variant = "primary",
  size = "md",
  className,
  children,
}: LinkProps) {
  return (
    <Link href={href} className={classes(variant, size, className)}>
      {children}
    </Link>
  );
}
