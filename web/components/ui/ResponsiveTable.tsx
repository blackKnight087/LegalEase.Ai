import { ReactNode } from "react";

/** Wrap wide tables so they scroll horizontally on phones. */
export default function ResponsiveTable({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={`le-table-wrap -mx-1 px-1 ${className}`}>
      <div className="inline-block min-w-full align-middle">{children}</div>
    </div>
  );
}
