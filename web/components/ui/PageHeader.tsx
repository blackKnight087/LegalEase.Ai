import { ReactNode } from "react";

export default function PageHeader({
  title,
  subtitle,
  eyebrow,
  children,
  sticky = true,
}: {
  title: string;
  subtitle?: string;
  eyebrow?: string;
  children?: ReactNode;
  sticky?: boolean;
}) {
  return (
    <>
      {/* Mobile: action bar only (title is in MobileTopBar) */}
      {subtitle && !children ? (
        <div className="lg:hidden shrink-0 border-b border-slate-200/80 bg-white/90 px-3 py-1">
          <p className="text-[10px] text-slate-500 m-0 leading-snug line-clamp-1">{subtitle}</p>
        </div>
      ) : null}
      {children ? (
        <div className="lg:hidden shrink-0 border-b border-slate-200/90 bg-white/95 backdrop-blur-sm">
          <div className="px-3 py-2 flex gap-2 overflow-x-auto touch-scroll-x items-center [&>*]:shrink-0 [&_button]:min-h-[40px] [&_a]:min-h-[40px]">
            {children}
          </div>
        </div>
      ) : null}

      {/* Desktop / large tablet: full header */}
      <header
        className={[
          "hidden lg:block shrink-0 border-b border-slate-200/90 bg-white/90 backdrop-blur-md",
          sticky ? "sticky top-0 z-20" : "",
        ].join(" ")}
      >
        <div className="px-6 lg:px-8 py-4 lg:py-5">
          <div className="flex flex-row items-center justify-between gap-4">
            <div className="min-w-0 animate-fade-in">
              {eyebrow && <p className="le-eyebrow m-0">{eyebrow}</p>}
              <h1 className="font-serif text-2xl lg:text-[1.65rem] font-bold text-slate-900 m-0 leading-tight tracking-tight">
                {title}
              </h1>
              {subtitle && (
                <p className="text-slate-500 text-sm mt-1.5 m-0 max-w-2xl leading-relaxed">
                  {subtitle}
                </p>
              )}
            </div>
            {children && (
              <div className="flex flex-wrap items-center justify-end gap-2 shrink-0">
                {children}
              </div>
            )}
          </div>
        </div>
      </header>
    </>
  );
}
