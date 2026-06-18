"use client";

export type PieSlice = {
  label: string;
  value: number;
  color?: string;
};

const DEFAULT_COLORS = [
  "#1e3a5f",
  "#2563eb",
  "#059669",
  "#7c3aed",
  "#d97706",
  "#dc2626",
  "#0891b2",
  "#64748b",
];

function polar(cx: number, cy: number, r: number, deg: number) {
  const rad = ((deg - 90) * Math.PI) / 180;
  return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) };
}

function slicePath(cx: number, cy: number, r: number, start: number, end: number) {
  const s = polar(cx, cy, r, start);
  const e = polar(cx, cy, r, end);
  const large = end - start > 180 ? 1 : 0;
  return `M ${cx} ${cy} L ${s.x} ${s.y} A ${r} ${r} 0 ${large} 1 ${e.x} ${e.y} Z`;
}

type Props = {
  title?: string;
  slices: PieSlice[];
  size?: number;
  /** Hide slices below this share of total (0–1). */
  minShare?: number;
  maxSlices?: number;
  emptyMessage?: string;
};

export default function AnalyticsPieChart({
  title,
  slices,
  size = 200,
  minShare = 0.02,
  maxSlices = 8,
  emptyMessage = "No data yet",
}: Props) {
  const raw = slices.filter((s) => s.value > 0);
  const total = raw.reduce((a, s) => a + s.value, 0);

  if (total <= 0) {
    return (
      <div>
        {title ? <p className="le-section-title mb-2">{title}</p> : null}
        <p className="text-sm text-slate-500">{emptyMessage}</p>
      </div>
    );
  }

  let sorted = [...raw].sort((a, b) => b.value - a.value);
  const main: PieSlice[] = [];
  let other = 0;
  for (let i = 0; i < sorted.length; i++) {
    const s = sorted[i];
    const share = s.value / total;
    if (main.length < maxSlices - 1 && share >= minShare) {
      main.push(s);
    } else {
      other += s.value;
    }
  }
  if (other > 0) {
    main.push({ label: "Other", value: other, color: "#94a3b8" });
  }

  const cx = size / 2;
  const cy = size / 2;
  const r = size * 0.38;
  let angle = 0;
  const arcs = main.map((s, i) => {
    const sweep = (s.value / total) * 360;
    const start = angle;
    const end = angle + sweep;
    angle = end;
    const color = s.color || DEFAULT_COLORS[i % DEFAULT_COLORS.length];
    return { ...s, start, end, color, pct: Math.round((s.value / total) * 100) };
  });

  return (
    <div>
      {title ? <p className="le-section-title mb-3">{title}</p> : null}
      <div className="flex flex-col sm:flex-row items-center gap-6">
        <svg
          width={size}
          height={size}
          viewBox={`0 0 ${size} ${size}`}
          className="shrink-0"
          role="img"
          aria-label={title || "Pie chart"}
        >
          {arcs.map((a) => (
            <path
              key={a.label}
              d={slicePath(cx, cy, r, a.start, a.end - 0.01)}
              fill={a.color}
              stroke="#fff"
              strokeWidth={1.5}
            />
          ))}
          <circle cx={cx} cy={cy} r={r * 0.45} fill="#f8fafc" />
          <text
            x={cx}
            y={cy - 4}
            textAnchor="middle"
            className="fill-navy text-[0.65rem] font-bold"
            style={{ fontSize: 11 }}
          >
            {total.toLocaleString()}
          </text>
          <text
            x={cx}
            y={cy + 10}
            textAnchor="middle"
            className="fill-slate-500"
            style={{ fontSize: 9 }}
          >
            total
          </text>
        </svg>
        <ul className="flex-1 w-full space-y-2 text-sm min-w-0">
          {arcs.map((a) => (
            <li key={a.label} className="flex items-center gap-2 min-w-0">
              <span
                className="w-3 h-3 rounded-sm shrink-0"
                style={{ backgroundColor: a.color }}
              />
              <span className="truncate text-slate-700 flex-1" title={a.label}>
                {a.label.replace(/_/g, " ")}
              </span>
              <span className="font-semibold text-navy shrink-0">{a.value}</span>
              <span className="text-xs text-slate-500 shrink-0 w-10 text-right">{a.pct}%</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
