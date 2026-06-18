import { ReactNode } from "react";
import { ButtonLink } from "./Button";

export default function EmptyState({
  icon = "📋",
  title,
  description,
  actionHref,
  actionLabel,
  children,
}: {
  icon?: string;
  title: string;
  description?: string;
  actionHref?: string;
  actionLabel?: string;
  children?: ReactNode;
}) {
  return (
    <div className="le-empty">
      <span className="text-4xl mb-3 opacity-80" aria-hidden>
        {icon}
      </span>
      <p className="text-base font-semibold text-slate-800 m-0">{title}</p>
      {description && (
        <p className="text-sm text-slate-500 mt-2 mb-0 max-w-sm leading-relaxed">{description}</p>
      )}
      {children}
      {actionHref && actionLabel && (
        <div className="mt-4">
          <ButtonLink href={actionHref} size="md">
            {actionLabel}
          </ButtonLink>
        </div>
      )}
    </div>
  );
}
