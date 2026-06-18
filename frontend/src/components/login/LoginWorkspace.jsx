import { motion } from "framer-motion";
import { useCinematicLoop } from "../../hooks/useCinematicLoop.js";
import CinematicViewport from "./CinematicViewport.jsx";
import LoginFormCard from "./LoginFormCard.jsx";

const CREAM = "#F3F4F6";
const EASE = [0.22, 1, 0.36, 1];

export default function LoginWorkspace(props) {
  const { phase, loginReady, skipToReady } = useCinematicLoop();

  return (
    <div
      className="flex-1 flex flex-col min-h-0 min-w-0"
      style={{
        background: `linear-gradient(160deg, #F4F4F2 0%, ${CREAM} 45%, #EFEFEA 100%)`,
      }}
    >
      <motion.div
        className="flex flex-col flex-1 min-h-0 w-full max-w-3xl mx-auto px-5 md:px-8 py-5 md:py-6"
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.85, ease: EASE }}
      >
        <div
          className="flex flex-col flex-1 min-h-0 rounded-2xl overflow-hidden"
          style={{
            background: CREAM,
            boxShadow: "0 16px 48px rgba(7, 20, 38, 0.08), 0 0 0 1px rgba(7, 20, 38, 0.04)",
          }}
        >
          <div className="flex items-center justify-between px-4 py-2 shrink-0 border-b border-slate-200/70">
            <p className="text-[0.62rem] tracking-[0.16em] uppercase m-0 font-semibold text-slate-500 font-sans">
              Legal Intelligence Console
            </p>
            <button
              type="button"
              onClick={skipToReady}
              className="text-[0.58rem] font-medium text-slate-400 hover:text-slate-700 transition-colors font-sans"
            >
              Skip cinematic
            </button>
          </div>

          <div className="flex flex-col flex-1 min-h-0">
            <CinematicViewport phase={phase} />
            <LoginFormCard {...props} loginReady={loginReady} />
          </div>
        </div>
      </motion.div>
    </div>
  );
}
