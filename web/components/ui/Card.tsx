import { ReactNode } from "react";

export function Card({
  children,
  className = "",
  padding = true,
  hover = false,
}: {
  children: ReactNode;
  className?: string;
  padding?: boolean;
  hover?: boolean;
}) {
  return (
    <div
      className={[
        "le-card",
        padding ? "p-5 sm:p-6" : "",
        hover ? "le-card-hover cursor-pointer" : "",
        className,
      ]
        .filter(Boolean)
        .join(" ")}
    >
      {children}
    </div>
  );
}

export function CardHeader({
  title,
  description,
  action,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3 mb-4">
      <div className="min-w-0">
        <h2 className="le-section-title m-0">{title}</h2>
        {description && <p className="le-section-desc mt-1 mb-0">{description}</p>}
      </div>
      {action ? <div className="shrink-0">{action}</div> : null}
    </div>
  );
}
