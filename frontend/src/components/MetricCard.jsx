export default function MetricCard({ icon, label, value }) {
  return (
    <div className="bg-white rounded-2xl p-5 border border-slate-200/80 shadow-sm hover:shadow-md transition-shadow">
      <span className="text-2xl">{icon}</span>
      <p className="text-xs text-slate-500 mt-3 font-medium uppercase tracking-wide">{label}</p>
      <p className="text-2xl font-bold text-navy mt-1">{value}</p>
    </div>
  );
}
