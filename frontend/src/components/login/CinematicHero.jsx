import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { useHeroIntro } from "../../hooks/useHeroIntro.js";
import BrandLogo from "./BrandLogo.jsx";

const EASE = [0.22, 1, 0.36, 1];
const NAVY = "#071426";
const GOLD = "#C8A24A";
const IVORY = "#F6F1E8";
const SILVER = "#B8C0CC";

const MICRO = [
  "Document Intelligence",
  "Constitutional Research",
  "Precedent Analysis",
  "Case Discovery",
  "OCR Legal Understanding",
];

function CourtroomSvg() {
  return (
    <svg className="absolute bottom-0 w-full h-[70%] opacity-35" viewBox="0 0 800 200" preserveAspectRatio="xMidYMax slice" aria-hidden>
      <path d="M280 80h240v28H280z" fill={SILVER} opacity="0.12" />
      <ellipse cx="400" cy="68" rx="50" ry="18" fill={SILVER} opacity="0.1" />
      <path d="M120 200V110c0-28 22-42 38-42s38 14 38 42v90" fill={IVORY} opacity="0.07" />
      <circle cx="158" cy="88" r="20" fill={IVORY} opacity="0.09" />
      <path d="M642 200V110c0-28 22-42 38-42s38 14 38 42v90" fill={IVORY} opacity="0.07" />
      <circle cx="680" cy="88" r="20" fill={IVORY} opacity="0.09" />
    </svg>
  );
}

function NetworkLines() {
  const lines = [
    [15, 25, 40, 50],
    [40, 50, 65, 30],
    [65, 30, 82, 55],
    [82, 55, 55, 72],
    [55, 72, 25, 65],
    [25, 65, 15, 25],
  ];
  return (
    <svg className="absolute inset-0 w-full h-full pointer-events-none" aria-hidden>
      {lines.map((c, i) => (
        <motion.line
          key={i}
          x1={`${c[0]}%`}
          y1={`${c[1]}%`}
          x2={`${c[2]}%`}
          y2={`${c[3]}%`}
          stroke={GOLD}
          strokeWidth="0.8"
          initial={{ opacity: 0 }}
          animate={{ opacity: 0.4 }}
          transition={{ delay: i * 0.1, duration: 1, ease: EASE }}
        />
      ))}
    </svg>
  );
}

function LogoCenter({ large = false }) {
  const sz = large ? "w-20 h-20 md:w-24 md:h-24" : "w-14 h-14";
  return (
    <div className="relative flex items-center justify-center">
      <motion.div
        className="absolute rounded-full border"
        style={{ width: 140, height: 140, borderColor: `${GOLD}33` }}
        animate={{ rotate: 360 }}
        transition={{ duration: 28, repeat: Infinity, ease: "linear" }}
      />
      <motion.div
        className="absolute rounded-full"
        style={{
          width: 100,
          height: 100,
          background: `radial-gradient(circle, ${GOLD}25 0%, transparent 70%)`,
        }}
        animate={{ scale: [1, 1.15, 1], opacity: [0.5, 0.8, 0.5] }}
        transition={{ duration: 3, repeat: Infinity, ease: "easeInOut" }}
      />
      <motion.div
        className="relative z-10"
        animate={{ scale: [1, 1.03, 1] }}
        transition={{ duration: 2.5, repeat: Infinity, ease: "easeInOut" }}
        style={{ filter: `drop-shadow(0 0 24px ${GOLD}55)` }}
      >
        <BrandLogo className={sz} />
      </motion.div>
    </div>
  );
}

function Scene1() {
  return (
    <motion.div
      className="absolute inset-0 flex items-center justify-center"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0, filter: "blur(4px)" }}
      transition={{ duration: 0.9, ease: EASE }}
    >
      <div
        className="absolute inset-0 opacity-40"
        style={{
          background: `radial-gradient(ellipse at 50% 40%, ${GOLD}20 0%, transparent 60%)`,
        }}
      />
      {[...Array(6)].map((_, i) => (
        <motion.div
          key={i}
          className="absolute w-1 h-1 rounded-full"
          style={{ background: GOLD, left: `${20 + i * 12}%`, top: `${30 + (i % 3) * 15}%` }}
          animate={{ opacity: [0.1, 0.5, 0.1], y: [0, -8, 0] }}
          transition={{ duration: 3, delay: i * 0.3, repeat: Infinity }}
        />
      ))}
      <motion.h2
        className="font-serif text-center m-0 px-6 relative z-10"
        style={{ color: IVORY, fontSize: "clamp(1.25rem, 2.5vw, 1.85rem)" }}
        initial={{ opacity: 0, y: 16, filter: "blur(6px)" }}
        animate={{ opacity: 1, y: 0, filter: "blur(0)" }}
        transition={{ duration: 1.2, delay: 0.2, ease: EASE }}
      >
        Justice Shapes Nations.
      </motion.h2>
    </motion.div>
  );
}

function Scene2() {
  return (
    <motion.div
      className="absolute inset-0"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.9, ease: EASE }}
    >
      <motion.div animate={{ x: [-4, 4, -4] }} transition={{ duration: 6, repeat: Infinity, ease: "easeInOut" }}>
        <CourtroomSvg />
      </motion.div>
    </motion.div>
  );
}

function Scene3() {
  return (
    <motion.div
      className="absolute inset-0 flex flex-col items-center justify-center"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.9, ease: EASE }}
    >
      <NetworkLines />
      <LogoCenter />
    </motion.div>
  );
}

function Scene4() {
  return (
    <motion.div
      className="absolute inset-0 flex flex-col items-center justify-center gap-3 px-6 text-center"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.9, ease: EASE }}
    >
      <LogoCenter large />
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3, ease: EASE }}>
        <h2 className="font-serif m-0" style={{ color: IVORY, fontSize: "clamp(1.1rem, 2vw, 1.5rem)" }}>
          The Intelligence Behind Modern Law
        </h2>
        <p className="text-[0.7rem] m-0 mt-2 max-w-md mx-auto leading-relaxed" style={{ color: `${SILVER}bb` }}>
          Constitutional reasoning, legal research, and precedent intelligence — powered by AI.
        </p>
      </motion.div>
    </motion.div>
  );
}

function Scene5() {
  const [idx, setIdx] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setIdx((i) => (i + 1) % MICRO.length), 800);
    return () => clearInterval(t);
  }, []);
  return (
    <motion.div
      className="absolute inset-0 flex flex-col items-center justify-center"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.9, ease: EASE }}
    >
      <LogoCenter />
      <div className="h-8 mt-4 relative w-full flex justify-center">
        <AnimatePresence mode="wait">
          <motion.span
            key={MICRO[idx]}
            className="absolute text-[0.65rem] tracking-[0.18em] uppercase font-medium"
            style={{ color: GOLD }}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            transition={{ duration: 0.5, ease: EASE }}
          >
            {MICRO[idx]}
          </motion.span>
        </AnimatePresence>
      </div>
    </motion.div>
  );
}

export default function CinematicHero() {
  const { phase, complete, skip, seen } = useHeroIntro();

  return (
    <section
      className="relative flex-1 min-h-0 mx-4 mt-3 rounded-2xl overflow-hidden shrink"
      style={{
        maxHeight: "min(48vh, 400px)",
        minHeight: "200px",
        background: `linear-gradient(145deg, #0a1a30 0%, ${NAVY} 55%, #050d18 100%)`,
        border: `1px solid ${GOLD}15`,
        boxShadow: `inset 0 1px 0 ${GOLD}10, 0 8px 32px rgba(0,0,0,0.35)`,
      }}
    >
      <motion.div
        className="absolute inset-0 pointer-events-none"
        animate={{ opacity: [0.3, 0.5, 0.3] }}
        transition={{ duration: 4, repeat: Infinity, ease: "easeInOut" }}
        style={{
          background: `radial-gradient(ellipse at 30% 20%, ${GOLD}12 0%, transparent 50%)`,
        }}
      />

      <AnimatePresence mode="wait">
        {phase === 0 && <Scene1 key="s1" />}
        {phase === 1 && <Scene2 key="s2" />}
        {phase === 2 && <Scene3 key="s3" />}
        {phase === 3 && <Scene4 key="s4" />}
        {phase === 4 && <Scene5 key="s5" />}
      </AnimatePresence>

      {complete && (
        <motion.div
          className="absolute inset-0 flex flex-col items-center justify-center gap-2 px-6 text-center"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 1, ease: EASE }}
        >
          <LogoCenter large />
          <h2 className="font-serif m-0 text-lg" style={{ color: IVORY }}>
            The Intelligence Behind Modern Law
          </h2>
          <p className="text-[0.68rem] m-0 max-w-sm" style={{ color: `${SILVER}aa` }}>
            Constitutional reasoning, legal research, and precedent intelligence — powered by AI.
          </p>
        </motion.div>
      )}

      {!complete && (
        <button
          type="button"
          onClick={skip}
          className="absolute top-2 right-2 z-20 px-2.5 py-1 rounded-full text-[0.6rem] font-semibold border opacity-70 hover:opacity-100 transition-opacity"
          style={{ color: SILVER, borderColor: `${SILVER}33`, background: `${NAVY}aa` }}
        >
          Skip
        </button>
      )}

      {seen && !complete && (
        <span
          className="absolute bottom-2 left-0 right-0 text-center text-[0.58rem] z-10"
          style={{ color: `${SILVER}44` }}
        >
          Short intro
        </span>
      )}
    </section>
  );
}
