import { motion } from "framer-motion";
import LegalEaseLogo from "../../LegalEaseLogo.jsx";
import { EASE, GOLD, IVORY } from "./chamberConstants.js";

export default function LogoReveal({ phase, showTagline, syncPulse }) {
  const visible = phase >= 3;
  const revealing = phase === 3;
  const settled = phase >= 4;

  return (
    <div className="absolute inset-0 flex flex-col items-center justify-center z-20 pointer-events-none">
      {/* Cinematic spotlight */}
      <motion.div
        className="absolute rounded-full pointer-events-none"
        style={{
          width: "min(280px, 55vw)",
          height: "min(280px, 55vw)",
          background: `radial-gradient(circle, ${GOLD}22 0%, rgba(0,110,255,0.08) 40%, transparent 70%)`,
        }}
        initial={false}
        animate={{
          opacity: visible ? [0.4, 0.85, 0.4] : 0,
          scale: revealing ? [0.9, 1.05, 1] : 1,
        }}
        transition={{
          opacity: { duration: syncPulse ? 2.2 : 4, repeat: Infinity, ease: "easeInOut" },
          scale: { duration: 1.4, ease: EASE },
        }}
      />

      <motion.div
        initial={false}
        animate={{
          opacity: visible ? 1 : 0,
          scale: revealing ? [0.85, 1] : settled ? 1 : 0.85,
        }}
        transition={{ duration: 1.35, ease: EASE }}
        className="flex flex-col items-center gap-3"
      >
        <div className={visible ? "hero-logo" : ""}>
          <LegalEaseLogo size={180} showText={false} />
        </div>
      </motion.div>

      {showTagline && (
        <motion.p
          className="font-serif text-center m-0 px-6 mt-4 relative z-10"
          style={{
            color: IVORY,
            fontSize: "clamp(0.85rem, 1.6vw, 1.1rem)",
            letterSpacing: "0.04em",
          }}
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 0.95, y: 0 }}
          transition={{ duration: 1.1, ease: EASE }}
        >
          The Intelligence Behind Modern Law
        </motion.p>
      )}
    </div>
  );
}
