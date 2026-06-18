import { motion } from "framer-motion";
import { CHAMBER, GOLD, SILVER, EASE } from "./chamberConstants.js";

const FIGURE_GRAD = "figureDissolve";

function FigureDefs() {
  return (
    <defs>
      <linearGradient id={FIGURE_GRAD} x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stopColor="#0a1420" stopOpacity="0.95" />
        <stop offset="55%" stopColor="#000" stopOpacity="0.75" />
        <stop offset="100%" stopColor={CHAMBER} stopOpacity="0" />
      </linearGradient>
      <linearGradient id="rimGoldL" x1="1" y1="0" x2="0" y2="1">
        <stop offset="0%" stopColor={GOLD} stopOpacity="0.55" />
        <stop offset="100%" stopColor={GOLD} stopOpacity="0" />
      </linearGradient>
      <linearGradient id="rimGoldR" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0%" stopColor={GOLD} stopOpacity="0.55" />
        <stop offset="100%" stopColor={GOLD} stopOpacity="0" />
      </linearGradient>
      <filter id="softGlow">
        <feGaussianBlur stdDeviation="2" result="blur" />
        <feMerge>
          <feMergeNode in="blur" />
          <feMergeNode in="SourceGraphic" />
        </feMerge>
      </filter>
    </defs>
  );
}

/** Left counsel — adversarial argument silhouette */
function LawyerLeft() {
  return (
    <g>
      {/* Rim light edge */}
      <path
        d="M118 218V118c0-28 22-42 38-42 8 0 16 3 22 9 4-14 14-22 28-22 12 0 22 6 28 16V218"
        fill="url(#rimGoldL)"
        opacity="0.35"
      />
      <path
        d="M120 220V120c0-30 24-46 40-46 10 0 18 4 24 11 5-16 16-25 32-25 14 0 26 8 32 20V220"
        fill="url(#figureDissolve)"
      />
      {/* Head — abstract, no facial detail */}
      <ellipse cx="168" cy="88" rx="20" ry="24" fill="#000" opacity="0.82" />
      {/* Collar / robe lapel hint */}
      <path d="M152 112 L168 128 L184 112" fill="none" stroke={SILVER} strokeWidth="0.8" opacity="0.2" />
      {/* Brief argument gesture — arm forward */}
      <path
        d="M200 145 Q228 132 240 118"
        fill="none"
        stroke="#000"
        strokeWidth="14"
        strokeLinecap="round"
        opacity="0.5"
      />
      <motion.path
        d="M200 145 Q228 132 240 118"
        fill="none"
        stroke={GOLD}
        strokeWidth="0.6"
        opacity="0.35"
        animate={{ opacity: [0.2, 0.5, 0.2] }}
        transition={{ duration: 3.5, repeat: Infinity, ease: "easeInOut" }}
      />
    </g>
  );
}

/** Right counsel — mirrored discourse */
function LawyerRight() {
  return (
    <g transform="scale(-1,1) translate(-900,0)">
      <path
        d="M118 218V118c0-28 22-42 38-42 8 0 16 3 22 9 4-14 14-22 28-22 12 0 22 6 28 16V218"
        fill="url(#rimGoldR)"
        opacity="0.35"
      />
      <path
        d="M120 220V120c0-30 24-46 40-46 10 0 18 4 24 11 5-16 16-25 32-25 14 0 26 8 32 20V220"
        fill="url(#figureDissolve)"
      />
      <ellipse cx="168" cy="88" rx="20" ry="24" fill="#000" opacity="0.82" />
      <path d="M152 112 L168 128 L184 112" fill="none" stroke={SILVER} strokeWidth="0.8" opacity="0.2" />
      <path
        d="M200 145 Q228 132 240 118"
        fill="none"
        stroke="#000"
        strokeWidth="14"
        strokeLinecap="round"
        opacity="0.5"
      />
      <motion.path
        d="M200 145 Q228 132 240 118"
        fill="none"
        stroke={GOLD}
        strokeWidth="0.6"
        opacity="0.35"
        animate={{ opacity: [0.2, 0.5, 0.2] }}
        transition={{ duration: 3.5, repeat: Infinity, ease: "easeInOut", delay: 0.6 }}
      />
    </g>
  );
}

/** Judge — symbolic authority behind constitutional axis */
function JudgePresence() {
  return (
    <g filter="url(#softGlow)">
      {/* Bench platform */}
      <ellipse cx="450" cy="118" rx="120" ry="14" fill={SILVER} opacity="0.06" />
      <path d="M330 118h240v10H330z" fill="#000" opacity="0.25" />
      {/* Robes — wide judicial silhouette */}
      <path
        d="M360 118 V72 Q450 48 540 72 V118 Q450 128 360 118 Z"
        fill="#000"
        opacity="0.55"
      />
      {/* Shoulders / mantle */}
      <path
        d="M385 72 Q450 58 515 72 L540 95 Q450 88 360 95 Z"
        fill="#000"
        opacity="0.65"
      />
      {/* Head — abstract oval, no face */}
      <ellipse cx="450" cy="62" rx="28" ry="32" fill="#000" opacity="0.7" />
      {/* Gold rim — authority edge light */}
      <motion.path
        d="M385 72 Q450 52 515 72"
        fill="none"
        stroke={GOLD}
        strokeWidth="1"
        animate={{ opacity: [0.25, 0.6, 0.25] }}
        transition={{ duration: 4, repeat: Infinity, ease: "easeInOut" }}
      />
      {/* Subtle gavel line — symbolic only */}
      <line x1="520" y1="95" x2="548" y2="88" stroke={GOLD} strokeWidth="0.5" opacity="0.25" />
    </g>
  );
}

export default function LegalFigures({ lawyersOpacity, judgeOpacity }) {
  return (
    <div className="absolute inset-0 pointer-events-none" aria-hidden>
      <motion.svg
        className="absolute bottom-0 w-full h-[72%]"
        viewBox="0 0 900 240"
        preserveAspectRatio="xMidYMax slice"
        initial={false}
        animate={{ opacity: lawyersOpacity, y: lawyersOpacity > 0 ? [4, 0, 4] : 0 }}
        transition={{
          opacity: { duration: 1.4, ease: EASE },
          y: { duration: 9, repeat: Infinity, ease: "easeInOut" },
        }}
      >
        <FigureDefs />
        <LawyerLeft />
        <LawyerRight />
      </motion.svg>

      <motion.svg
        className="absolute top-[8%] left-0 w-full h-[48%]"
        viewBox="0 0 900 200"
        preserveAspectRatio="xMidYMid meet"
        initial={false}
        animate={{
          opacity: judgeOpacity,
          scale: judgeOpacity > 0 ? [1, 1.015, 1] : 1,
        }}
        transition={{
          opacity: { duration: 1.6, ease: EASE },
          scale: { duration: 8, repeat: Infinity, ease: "easeInOut" },
        }}
      >
        <FigureDefs />
        <JudgePresence />
      </motion.svg>
    </div>
  );
}
