import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { useCinematicIntro } from "../../hooks/useCinematicIntro.js";
import LoginVault from "./LoginVault.jsx";

const EASE = [0.22, 1, 0.36, 1];
const NAVY = "#071426";
const GOLD = "#C8A24A";
const IVORY = "#F6F1E8";
const SILVER = "#B8C0CC";

const FLOAT_WORDS = [
  "Justice",
  "Constitution",
  "Equality",
  "Rights",
  "Judgment",
  "Precedent",
];

const MICRO_CAPS = [
  "Document Intelligence",
  "Constitutional Research",
  "Case Intelligence",
  "Precedent Analysis",
  "OCR Legal Understanding",
  "Contract Intelligence",
];

function GoldenBeam() {
  return (
    <motion.div
      className="absolute inset-0 pointer-events-none"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 1.8, ease: EASE }}
    >
      <div
        className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[140%] h-[80%]"
        style={{
          background: `radial-gradient(ellipse at 50% 45%, ${GOLD}33 0%, transparent 55%)`,
          filter: "blur(40px)",
        }}
      />
      <motion.div
        className="absolute inset-0 opacity-30"
        style={{
          background: `linear-gradient(105deg, transparent 40%, ${GOLD}22 50%, transparent 60%)`,
        }}
        animate={{ x: ["-20%", "20%"] }}
        transition={{ duration: 4, repeat: Infinity, repeatType: "reverse", ease: "easeInOut" }}
      />
    </motion.div>
  );
}

function ManuscriptTexture() {
  return (
    <div
      className="absolute inset-0 opacity-[0.07] pointer-events-none mix-blend-overlay"
      style={{
        backgroundImage: `repeating-linear-gradient(0deg, transparent, transparent 28px, ${IVORY} 28px, ${IVORY} 29px)`,
      }}
    />
  );
}

function FloatingLegalWords() {
  return (
    <div className="absolute inset-0 overflow-hidden pointer-events-none">
      {FLOAT_WORDS.map((word, i) => (
        <motion.span
          key={word}
          className="absolute font-serif text-xs tracking-[0.25em] uppercase"
          style={{
            color: `${SILVER}40`,
            left: `${12 + (i % 3) * 28}%`,
            top: `${15 + Math.floor(i / 3) * 30}%`,
          }}
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: [0, 0.5, 0.25], y: [10, 0, -6] }}
          transition={{ duration: 2.5, delay: i * 0.15, ease: EASE }}
        >
          {word}
        </motion.span>
      ))}
    </div>
  );
}

function Phase1LawOfLand() {
  return (
    <motion.div
      className="absolute inset-0 flex flex-col items-center justify-center z-10 px-8"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0, filter: "blur(6px)" }}
      transition={{ duration: 1.2, ease: EASE }}
    >
      <GoldenBeam />
      <ManuscriptTexture />
      <FloatingLegalWords />
      <motion.h1
        className="font-serif text-center max-w-3xl relative z-20 m-0"
        style={{ color: IVORY, fontSize: "clamp(1.75rem, 4vw, 3rem)" }}
        initial={{ opacity: 0, y: 24, filter: "blur(8px)" }}
        animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
        transition={{ duration: 1.6, delay: 0.4, ease: EASE }}
      >
        Every Nation Is Built On Law.
      </motion.h1>
    </motion.div>
  );
}

function CourtroomSilhouettes() {
  return (
    <svg
      className="absolute bottom-0 left-0 right-0 w-full h-[55%] opacity-40"
      viewBox="0 0 1200 400"
      preserveAspectRatio="xMidYMax slice"
      aria-hidden
    >
      <defs>
        <linearGradient id="silGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={NAVY} stopOpacity="0" />
          <stop offset="100%" stopColor={NAVY} stopOpacity="0.9" />
        </linearGradient>
      </defs>
      <rect width="1200" height="400" fill="url(#silGrad)" />
      <path d="M420 120h360v40H420z" fill={SILVER} opacity="0.15" />
      <ellipse cx="600" cy="100" rx="80" ry="28" fill={SILVER} opacity="0.12" />
      <path d="M180 400V200c0-40 30-60 50-60s50 20 50 60v200" fill={IVORY} opacity="0.08" />
      <circle cx="230" cy="165" r="28" fill={IVORY} opacity="0.1" />
      <path d="M920 400V200c0-40 30-60 50-60s50 20 50 60v200" fill={IVORY} opacity="0.08" />
      <circle cx="970" cy="165" r="28" fill={IVORY} opacity="0.1" />
    </svg>
  );
}

function Phase2HumanJustice() {
  return (
    <motion.div
      className="absolute inset-0 z-10"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 1.2, ease: EASE }}
    >
      <motion.div
        animate={{ scale: [1, 1.03] }}
        transition={{ duration: 4, ease: EASE }}
        className="absolute inset-0"
      >
        <CourtroomSilhouettes />
      </motion.div>
      <motion.h2
        className="absolute top-[38%] left-0 right-0 text-center font-serif px-8 m-0 z-20"
        style={{ color: IVORY, fontSize: "clamp(1.5rem, 3.5vw, 2.5rem)" }}
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 1.4, delay: 0.3, ease: EASE }}
      >
        Every Decision Shapes Lives.
      </motion.h2>
    </motion.div>
  );
}

function IntelligenceNetwork() {
  const lines = [
    [20, 30, 45, 55],
    [45, 55, 70, 25],
    [70, 25, 80, 60],
    [80, 60, 55, 75],
    [55, 75, 30, 65],
    [30, 65, 20, 30],
  ];
  return (
    <svg className="absolute inset-0 w-full h-full" aria-hidden>
      {lines.map((coords, i) => (
        <motion.line
          key={i}
          x1={`${coords[0]}%`}
          y1={`${coords[1]}%`}
          x2={`${coords[2]}%`}
          y2={`${coords[3]}%`}
          stroke={GOLD}
          strokeWidth="1"
          initial={{ opacity: 0 }}
          animate={{ opacity: 0.35 }}
          transition={{ duration: 1.5, delay: i * 0.12, ease: EASE }}
        />
      ))}
    </svg>
  );
}

function ScalesLogoHero({ size = "large" }) {
  const dim = size === "large" ? "w-24 h-24 md:w-32 md:h-32" : "w-16 h-16";
  return (
    <div className="relative flex items-center justify-center">
      {[1, 2, 3].map((ring) => (
        <motion.div
          key={ring}
          className="absolute rounded-full border"
          style={{
            width: 120 + ring * 48,
            height: 120 + ring * 48,
            borderColor: `${GOLD}${ring === 1 ? "55" : ring === 2 ? "33" : "18"}`,
          }}
          animate={{ rotate: ring % 2 === 0 ? 360 : -360 }}
          transition={{ duration: 24 + ring * 8, repeat: Infinity, ease: "linear" }}
        />
      ))}
      <motion.div
        className="relative z-10 rounded-full p-4"
        style={{ boxShadow: `0 0 60px ${GOLD}44, 0 0 120px ${GOLD}22` }}
        animate={{ scale: [1, 1.04, 1] }}
        transition={{ duration: 3, repeat: Infinity, ease: "easeInOut" }}
      >
        <img src="/scales-logo.svg" alt="LegalEase" className={dim} width={128} height={128} />
      </motion.div>
    </div>
  );
}

function Phase3LawIntelligence() {
  return (
    <motion.div
      className="absolute inset-0 flex flex-col items-center justify-center z-10"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 1.2, ease: EASE }}
    >
      <IntelligenceNetwork />
      <motion.div
        className="mb-10"
        initial={{ opacity: 0, scale: 0.85 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 1.4, ease: EASE }}
      >
        <ScalesLogoHero />
      </motion.div>
      <motion.h2
        className="font-serif text-center m-0 px-6"
        style={{ color: IVORY, fontSize: "clamp(1.4rem, 3vw, 2.25rem)" }}
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.5, duration: 1.2, ease: EASE }}
      >
        Where Law Meets Intelligence.
      </motion.h2>
    </motion.div>
  );
}

function Phase4Future() {
  const [idx, setIdx] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setIdx((i) => (i + 1) % MICRO_CAPS.length), 900);
    return () => clearInterval(t);
  }, []);

  return (
    <motion.div
      className="absolute inset-0 flex flex-col items-center justify-center z-10"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 1.2, ease: EASE }}
    >
      <motion.div
        className="absolute inset-0 opacity-15"
        style={{
          backgroundImage: `linear-gradient(${SILVER}22 1px, transparent 1px)`,
          backgroundSize: "100% 48px",
        }}
        animate={{ backgroundPositionY: ["0px", "48px"] }}
        transition={{ duration: 8, repeat: Infinity, ease: "linear" }}
      />
      <ScalesLogoHero size="medium" />
      <div className="h-12 mt-8 relative w-full max-w-md flex justify-center">
        <AnimatePresence mode="wait">
          <motion.p
            key={MICRO_CAPS[idx]}
            className="absolute font-sans text-sm tracking-[0.2em] uppercase m-0"
            style={{ color: GOLD }}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.6, ease: EASE }}
          >
            {MICRO_CAPS[idx]}
          </motion.p>
        </AnimatePresence>
      </div>
    </motion.div>
  );
}

export default function CinematicStoryLogin({
  tab,
  setTab,
  username,
  setUsername,
  password,
  setPassword,
  confirm,
  setConfirm,
  error,
  busy,
  onSubmit,
}) {
  const { phase, showLogin, skip, introSeen } = useCinematicIntro();
  const [soundOn, setSoundOn] = useState(false);
  const revealLogin = showLogin || phase >= 4;

  return (
    <div className="fixed inset-0 overflow-hidden" style={{ background: NAVY, color: IVORY }}>
      <motion.div
        className="absolute inset-0"
        animate={{
          background: [
            `radial-gradient(ellipse 90% 70% at 50% 100%, #0a2848 0%, ${NAVY} 70%)`,
            `radial-gradient(ellipse 80% 60% at 50% 40%, #0d3258 0%, ${NAVY} 75%)`,
          ],
        }}
        transition={{ duration: 10, ease: EASE }}
      />

      <AnimatePresence mode="wait">
        {phase === 0 && <Phase1LawOfLand key="p1" />}
        {phase === 1 && <Phase2HumanJustice key="p2" />}
        {phase === 2 && <Phase3LawIntelligence key="p3" />}
        {phase === 3 && <Phase4Future key="p4" />}
      </AnimatePresence>

      {/* Phase 5 — login emerges from story */}
      <motion.div
        className="absolute inset-0 flex flex-col items-center justify-center z-30 px-6 pointer-events-none"
        initial={false}
      >
        <motion.div
          className="w-full max-w-[400px] pointer-events-auto"
          initial={{ opacity: 0, y: 40, scale: 0.96, filter: "blur(14px)" }}
          animate={
            revealLogin
              ? { opacity: 1, y: 0, scale: 1, filter: "blur(0px)" }
              : { opacity: 0, y: 40, scale: 0.96, filter: "blur(14px)" }
          }
          transition={{ duration: 1.8, ease: EASE }}
        >
          <motion.div
            className="flex justify-center mb-5"
            animate={revealLogin ? { scale: [1.08, 1] } : {}}
            transition={{ duration: 2, ease: EASE }}
          >
            <ScalesLogoHero size="small" />
          </motion.div>
          <div className="text-center mb-6">
            <h1
              className="font-serif m-0 mb-2"
              style={{ fontSize: "clamp(1.75rem, 4vw, 2.25rem)", color: IVORY }}
            >
              Enter LegalEase.AI
            </h1>
            <p className="text-sm m-0 mb-1" style={{ color: SILVER }}>
              India&apos;s AI-powered constitutional and legal intelligence system.
            </p>
            <p className="text-xs italic m-0" style={{ color: `${GOLD}cc` }}>
              Research deeper. Reason smarter. Practice better.
            </p>
          </div>
          <LoginVault
            tab={tab}
            setTab={setTab}
            username={username}
            setUsername={setUsername}
            password={password}
            setPassword={setPassword}
            confirm={confirm}
            setConfirm={setConfirm}
            error={error}
            busy={busy}
            onSubmit={onSubmit}
          />
        </motion.div>
      </motion.div>

      {!revealLogin && (
        <motion.button
          type="button"
          onClick={skip}
          className="absolute top-6 right-6 z-50 px-4 py-2 rounded-full text-xs font-semibold tracking-wide border"
          style={{
            color: SILVER,
            borderColor: `${SILVER}44`,
            background: `${NAVY}cc`,
          }}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.8 }}
          whileHover={{ borderColor: GOLD, color: IVORY }}
        >
          Skip Intro
        </motion.button>
      )}

      <button
        type="button"
        onClick={() => setSoundOn((s) => !s)}
        className="absolute top-6 left-6 z-50 px-3 py-2 rounded-full text-[0.65rem] font-medium border opacity-60 hover:opacity-100"
        style={{ color: SILVER, borderColor: `${SILVER}33`, background: `${NAVY}88` }}
      >
        {soundOn ? "Sound on" : "Sound off"}
      </button>

      {introSeen && !revealLogin && (
        <p
          className="absolute bottom-4 left-0 right-0 text-center text-[0.65rem] z-40 m-0"
          style={{ color: `${SILVER}55` }}
        >
          Welcome back — shortened intro
        </p>
      )}
    </div>
  );
}
