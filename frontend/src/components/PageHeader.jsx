export default function PageHeader({ title, subtitle, children }) {
  return (
    <header className="shrink-0 px-8 py-5 border-b border-slate-200/80 bg-white/50 backdrop-blur-sm">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="font-serif text-2xl font-bold text-navy m-0">{title}</h1>
          {subtitle && <p className="text-slate-500 text-sm mt-1 m-0">{subtitle}</p>}
        </div>
        {children}
      </div>
    </header>
  );
}
