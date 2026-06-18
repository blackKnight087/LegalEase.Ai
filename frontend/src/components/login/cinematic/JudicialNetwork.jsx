import { motion } from "framer-motion";
import { GOLD, EASE } from "./chamberConstants.js";

const NODES = [
  { id: "lawyerL", x: 22, y: 72, label: "Argument" },
  { id: "lawyerR", x: 78, y: 72, label: "Counter" },
  { id: "judge", x: 50, y: 32, label: "Authority" },
  { id: "core", x: 50, y: 52, label: null },
  { id: "prec1", x: 18, y: 38, label: "Art. 14" },
  { id: "prec2", x: 82, y: 36, label: "Precedent" },
  { id: "prec3", x: 35, y: 22, label: "§ 302" },
  { id: "prec4", x: 65, y: 24, label: "Judgment" },
  { id: "prec5", x: 50, y: 14, label: "Constitution" },
];

const EDGES = [
  ["lawyerL", "core"],
  ["lawyerR", "core"],
  ["judge", "core"],
  ["prec1", "lawyerL"],
  ["prec2", "lawyerR"],
  ["prec3", "judge"],
  ["prec4", "judge"],
  ["prec5", "judge"],
  ["prec1", "core"],
  ["prec2", "core"],
  ["prec3", "core"],
  ["prec4", "core"],
  ["prec5", "core"],
  ["lawyerL", "lawyerR"],
];

export default function JudicialNetwork({ opacity, pathwaysLit = false }) {
  const nodeMap = Object.fromEntries(NODES.map((n) => [n.id, n]));

  return (
    <motion.svg
      className="absolute inset-0 w-full h-full pointer-events-none"
      aria-hidden
      initial={false}
      animate={{ opacity }}
      transition={{ duration: 1.5, ease: EASE }}
    >
      <defs>
        <radialGradient id="nodeGlow">
          <stop offset="0%" stopColor={GOLD} stopOpacity="0.8" />
          <stop offset="100%" stopColor={GOLD} stopOpacity="0" />
        </radialGradient>
      </defs>

      {EDGES.map(([a, b], i) => {
        const na = nodeMap[a];
        const nb = nodeMap[b];
        if (!na || !nb) return null;
        return (
          <motion.line
            key={`${a}-${b}`}
            x1={`${na.x}%`}
            y1={`${na.y}%`}
            x2={`${nb.x}%`}
            y2={`${nb.y}%`}
            stroke={GOLD}
            strokeWidth={pathwaysLit ? 0.7 : 0.4}
            strokeDasharray={pathwaysLit ? "none" : "4 6"}
            animate={{
              opacity: pathwaysLit ? [0.35, 0.7, 0.35] : [0.08, 0.28, 0.08],
            }}
            transition={{
              duration: pathwaysLit ? 2.8 : 4,
              delay: i * 0.08,
              repeat: Infinity,
              ease: "easeInOut",
            }}
          />
        );
      })}

      {NODES.map((node, i) => (
        <g key={node.id}>
          <motion.circle
            cx={`${node.x}%`}
            cy={`${node.y}%`}
            r={node.id === "core" ? 3.5 : 2}
            fill="url(#nodeGlow)"
            animate={{ opacity: [0.2, pathwaysLit ? 0.85 : 0.45, 0.2], r: [2, node.id === "core" ? 4 : 2.8, 2] }}
            transition={{ duration: 3, delay: i * 0.15, repeat: Infinity, ease: "easeInOut" }}
          />
          {node.label && pathwaysLit && (
            <motion.text
              x={`${node.x}%`}
              y={`${node.y - 4}%`}
              textAnchor="middle"
              fill={GOLD}
              fontSize="7"
              fontFamily="Georgia, serif"
              animate={{ opacity: [0.25, 0.55, 0.25] }}
              transition={{ duration: 3.5, delay: i * 0.2, repeat: Infinity }}
            >
              {node.label}
            </motion.text>
          )}
        </g>
      ))}

      {pathwaysLit && (
        <motion.ellipse
          cx="50%"
          cy="52%"
          rx="12%"
          ry="8%"
          fill="none"
          stroke={GOLD}
          strokeWidth="0.35"
          animate={{ opacity: [0.12, 0.35, 0.12] }}
          transition={{ duration: 10, repeat: Infinity, ease: "easeInOut" }}
        />
      )}
    </motion.svg>
  );
}
