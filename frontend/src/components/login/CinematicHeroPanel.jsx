import { motion } from "framer-motion";
import LegalEaseLogo from "../LegalEaseLogo.jsx";

const EASE = [0.22, 1, 0.36, 1];
const GOLD = "#C8A24A";
const CHAMBER = "#0a0f18";

const PILLS = [
  {
    title: "RAG-Based Intelligence",
    desc: "Answers grounded in your uploaded legal documents",
  },
  {
    title: "Verdict-Grade Citations",
    desc: "Source-locked precision on every claim",
  },
  {
    title: "Court-Trusted Scope",
    desc: "Legal-only intelligence, nothing else",
  },
];

function GoldNetwork() {
  const nodes = [
    [50, 42],
    [28, 55],
    [72, 55],
    [35, 68],
    [65, 68],
    [50, 78],
    [18, 48],
    [82, 48],
  ];
  const edges = [
    [0, 1],
    [0, 2],
    [0, 3],
    [0, 4],
    [1, 3],
    [2, 4],
    [3, 5],
    [4, 5],
    [1, 6],
    [2, 7],
    [6, 1],
    [7, 2],
  ];

  return (
    <svg className="absolute inset-0 w-full h-full opacity-90" aria-hidden>
      {edges.map(([a, b], i) => (
        <motion.line
          key={i}
          x1={`${nodes[a][0]}%`}
          y1={`${nodes[a][1]}%`}
          x2={`${nodes[b][0]}%`}
          y2={`${nodes[b][1]}%`}
          stroke={GOLD}
          strokeWidth="0.5"
          animate={{ opacity: [0.2, 0.5, 0.2] }}
          transition={{ duration: 3.5, delay: i * 0.12, repeat: Infinity, ease: "easeInOut" }}
        />
      ))}
      {nodes.map(([x, y], i) => (
        <motion.circle
          key={i}
          cx={`${x}%`}
          cy={`${y}%`}
          r="2"
          fill={GOLD}
          animate={{ opacity: [0.35, 0.75, 0.35] }}
          transition={{ duration: 2.8, delay: i * 0.15, repeat: Infinity }}
        />
      ))}
    </svg>
  );
}

export default function CinematicHeroPanel() {
  return (
    <motion.section
      className="relative w-full rounded-2xl overflow-hidden shrink-0"
      style={{
        background: `linear-gradient(165deg, ${CHAMBER} 0%, #050810 100%)`,
        minHeight: "min(340px, 42vh)",
        boxShadow: "0 20px 50px rgba(7, 20, 38, 0.15)",
      }}
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 1, ease: EASE }}
    >
      <GoldNetwork />

      <motion.div
        className="absolute inset-0 pointer-events-none"
        style={{
          background: `radial-gradient(ellipse at 50% 35%, ${GOLD}14 0%, transparent 55%)`,
        }}
        animate={{ opacity: [0.6, 1, 0.6] }}
        transition={{ duration: 5, repeat: Infinity, ease: "easeInOut" }}
      />

      <div className="relative z-10 flex flex-col items-center justify-center text-center px-6 py-10 md:py-12 gap-3">
        <div className="hero-logo">
          <LegalEaseLogo size={96} showText={false} />
        </div>

        <p
          className="font-sans text-[0.6rem] tracking-[0.2em] uppercase m-0 font-semibold"
          style={{ color: GOLD }}
        >
          Your AI Powered Legal Assistant
        </p>

        <h2
          className="font-serif font-bold m-0 leading-tight max-w-lg"
          style={{ color: "#F6F1E8", fontSize: "clamp(1.35rem, 2.8vw, 1.85rem)" }}
        >
          The Intelligence Behind Modern Law
        </h2>

        <p
          className="font-sans m-0 max-w-md leading-relaxed"
          style={{ color: "rgba(184, 192, 204, 0.85)", fontSize: "clamp(0.72rem, 1.2vw, 0.82rem)" }}
        >
          Trusted legal intelligence grounded in precedent, constitutional reasoning, and
          citation-first analysis.
        </p>

        <div className="flex flex-wrap justify-center gap-2 mt-3 w-full max-w-2xl">
          {PILLS.map((pill, i) => (
            <motion.div
              key={pill.title}
              className="rounded-full px-3 py-1.5 text-left max-w-[220px]"
              style={{
                border: `1px solid ${GOLD}55`,
                background: "rgba(200, 162, 74, 0.08)",
              }}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.4 + i * 0.1, duration: 0.7, ease: EASE }}
            >
              <p className="m-0 font-sans text-[0.62rem] font-semibold" style={{ color: GOLD }}>
                {pill.title}
              </p>
              <p className="m-0 font-sans text-[0.55rem] leading-snug mt-0.5" style={{ color: "#94a3b8" }}>
                {pill.desc}
              </p>
            </motion.div>
          ))}
        </div>
      </div>
    </motion.section>
  );
}
