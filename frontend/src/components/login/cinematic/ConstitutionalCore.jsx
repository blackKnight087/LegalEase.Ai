import { motion } from "framer-motion";
import LegalEaseLogo from "../../LegalEaseLogo.jsx";
import { EASE, GOLD, IVORY } from "./chamberConstants.js";

export default function ConstitutionalCore({ opacity, assembled, showTagline, syncPulse }) {
  return (
    <motion.div
      className="absolute inset-0 flex flex-col items-center justify-center z-20 pointer-events-none"
      initial={false}
      animate={{ opacity }}
      transition={{ duration: 1.2, ease: EASE }}
    >
      {/* Monumental gold radiance */}
      <motion.div
        className="absolute rounded-full"
        style={{
          width: "min(220px, 42vw)",
          height: "min(220px, 42vw)",
          background: `radial-gradient(circle, ${GOLD}28 0%, ${GOLD}08 40%, transparent 70%)`,
        }}
        animate={{
          scale: syncPulse ? [1, 1.12, 1] : [1, 1.06, 1],
          opacity: [0.5, 0.85, 0.5],
        }}
        transition={{ duration: syncPulse ? 2.2 : 4, repeat: Infinity, ease: "easeInOut" }}
      />

      {/* Orbital intelligence ring */}
      <motion.div
        className="absolute rounded-full border"
        style={{
          width: "min(180px, 36vw)",
          height: "min(180px, 36vw)",
          borderColor: `${GOLD}35`,
        }}
        animate={{ rotate: 360 }}
        transition={{ duration: 36, repeat: Infinity, ease: "linear" }}
      />
      <motion.div
        className="absolute rounded-full border border-dashed"
        style={{
          width: "min(200px, 40vw)",
          height: "min(200px, 40vw)",
          borderColor: `${GOLD}18`,
        }}
        animate={{ rotate: -360 }}
        transition={{ duration: 48, repeat: Infinity, ease: "linear" }}
      />

      <motion.div
        className="relative flex flex-col items-center gap-2"
        style={{
          filter: assembled
            ? "drop-shadow(0 0 28px rgba(200,162,74,0.55)) drop-shadow(0 0 12px rgba(200,162,74,0.35))"
            : "none",
        }}
        animate={{
          y: assembled ? [0, -6, 0] : 8,
          scale: assembled ? (syncPulse ? [1, 1.03, 1] : [0.92, 1, 0.98, 1]) : 0.75,
          opacity: assembled ? 1 : 0,
        }}
        transition={{
          y: { duration: 5, repeat: Infinity, ease: "easeInOut" },
          scale: assembled
            ? syncPulse
              ? { duration: 2.2, repeat: Infinity, ease: "easeInOut" }
              : { duration: 1.6, ease: EASE }
            : { duration: 0.8, ease: EASE },
          opacity: { duration: 1.2, ease: EASE },
        }}
      >
        <div className="hero-logo">
          <LegalEaseLogo size={96} showText={false} />
        </div>
      </motion.div>

      {showTagline && (
        <motion.p
          className="font-serif text-center m-0 px-6 mt-3 relative z-10"
          style={{
            color: IVORY,
            fontSize: "clamp(0.8rem, 1.5vw, 1.05rem)",
            letterSpacing: "0.04em",
          }}
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 0.92, y: 0 }}
          transition={{ delay: 0.4, duration: 1.2, ease: EASE }}
        >
          The Intelligence Behind Modern Law
        </motion.p>
      )}
    </motion.div>
  );
}
