import { motion } from "framer-motion";
import ChamberBackdrop from "./cinematic/ChamberBackdrop.jsx";
import LegalFigures from "./cinematic/LegalFigures.jsx";
import JudicialNetwork from "./cinematic/JudicialNetwork.jsx";
import LogoReveal from "./cinematic/LogoReveal.jsx";
import { EASE, GOLD, IVORY } from "./cinematic/chamberConstants.js";

function beat(phase, start) {
  if (phase < start) return 0;
  if (phase === start) return 0.5;
  return 1;
}

export default function CinematicViewport({ phase }) {
  const lawyersOp = beat(phase, 1);
  const judgeOp = beat(phase, 1);
  const networkVisible = phase >= 2 ? 1 : beat(phase, 1) * 0.4;
  const pathwaysLit = phase >= 2;
  const showTagline = phase >= 4;
  const syncPulse = phase >= 4;

  return (
    <div
      className="relative w-full flex-1 min-h-[240px] md:min-h-[280px] overflow-hidden rounded-t-2xl"
      style={{ background: "#050c16" }}
    >
      <motion.div
        className="absolute inset-0"
        animate={{ scale: [1, 1.015, 1] }}
        transition={{ duration: 14, repeat: Infinity, ease: "easeInOut" }}
      >
        <ChamberBackdrop archiveOpacity={phase === 0 ? 1 : 0.8} />
        <JudicialNetwork opacity={networkVisible} pathwaysLit={pathwaysLit} />
        <LegalFigures lawyersOpacity={lawyersOp} judgeOpacity={judgeOp} />
        <LogoReveal phase={phase} showTagline={showTagline} syncPulse={syncPulse} />
      </motion.div>

      {phase === 0 && (
        <motion.p
          className="absolute top-[14%] left-0 right-0 z-30 text-center font-serif m-0 px-6 pointer-events-none"
          style={{ color: IVORY, fontSize: "clamp(0.95rem, 1.8vw, 1.35rem)", letterSpacing: "0.03em" }}
          initial={{ opacity: 0, filter: "blur(8px)" }}
          animate={{ opacity: 1, filter: "blur(0px)" }}
          transition={{ duration: 1.2, ease: EASE }}
        >
          Justice Shapes Nations
        </motion.p>
      )}

      {phase >= 4 && (
        <motion.p
          className="absolute bottom-4 left-0 right-0 z-30 text-center m-0 pointer-events-none font-sans"
          style={{ color: `${GOLD}99`, fontSize: "0.58rem", letterSpacing: "0.22em", textTransform: "uppercase" }}
          animate={{ opacity: [0.35, 0.8, 0.35] }}
          transition={{ duration: 2.5, repeat: Infinity, ease: "easeInOut" }}
        >
          System Ready
        </motion.p>
      )}
    </div>
  );
}
