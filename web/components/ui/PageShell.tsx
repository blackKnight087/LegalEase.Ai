import { ReactNode } from "react";

const MW: Record<string, string> = {
  "3xl": "max-w-3xl",
  "5xl": "max-w-5xl",
  "6xl": "max-w-6xl",
  "7xl": "max-w-7xl",
  full: "max-w-none",
};

export default function PageShell({
  children,
  maxWidth = "7xl",
  className = "",
}: {
  children: ReactNode;
  maxWidth?: keyof typeof MW | "full";
  className?: string;
}) {
  return (
    <div
      className={[
        "flex-1 overflow-y-auto overflow-x-hidden le-scroll le-page-body",
        MW[maxWidth] || MW["7xl"],
        "mx-auto w-full min-w-0",
        className,
      ]
        .filter(Boolean)
        .join(" ")}
    >
      {children}
    </div>
  );
}
