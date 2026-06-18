import { motion } from "framer-motion";
import LegalEaseLogo from "../LegalEaseLogo.jsx";
import { SIDEBAR_FEATURES } from "../../data/loginSidebarFeatures.js";

const EASE = [0.22, 1, 0.36, 1];
const NAVY = "#071426";
const GOLD = "#C8A24A";
const IVORY = "#F6F1E8";
const SILVER = "#B8C0CC";

export default function LoginSidebar() {
  return (
    <aside
      className="w-[280px] shrink-0 h-full flex flex-col overflow-hidden"
      style={{
        background: `linear-gradient(175deg, #0a1c34 0%, ${NAVY} 45%, #061222 100%)`,
        borderRight: `1px solid ${GOLD}22`,
        boxShadow: "4px 0 28px rgba(0,0,0,0.14)",
      }}
    >
      <div className="brand-section shrink-0 px-3">
        <LegalEaseLogo size={52} showText align="left" />
        <h1 className="brand-title m-0">LegalEase.AI</h1>
        <p className="brand-subtitle m-0">AI-Powered Legal Intelligence</p>
      </div>

      <div className="px-4 pb-2 shrink-0">
        <h2 className="font-sans text-[0.72rem] font-bold m-0 mb-1" style={{ color: IVORY }}>
          Platform Capabilities
        </h2>
        <p className="font-sans text-[0.6rem] m-0 leading-snug" style={{ color: `${SILVER}80` }}>
          Explore what LegalEase.AI delivers before you sign in.
        </p>
      </div>

      <nav className="flex-1 min-h-0 overflow-y-auto le-scroll px-3 pb-3 space-y-1">
        {SIDEBAR_FEATURES.map((f, i) => (
          <motion.div
            key={f.title}
            initial={{ opacity: 0, x: -8 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: 0.05 * i, duration: 0.5, ease: EASE }}
            whileHover={{
              y: -1,
              borderColor: `${GOLD}45`,
              boxShadow: `0 4px 16px ${GOLD}15`,
              backgroundColor: "rgba(255,255,255,0.05)",
            }}
            className="flex gap-2.5 p-2 rounded-lg border cursor-default transition-all duration-300 relative overflow-hidden"
            style={{
              borderColor: "rgba(255,255,255,0.08)",
              background: "rgba(255,255,255,0.03)",
            }}
          >
            <span
              className="absolute left-0 top-2 bottom-2 w-0.5 rounded-full"
              style={{ background: `linear-gradient(180deg, ${GOLD}88, ${GOLD}33)` }}
            />
            <span className="text-base shrink-0 pl-1.5" aria-hidden>
              {f.icon}
            </span>
            <div className="min-w-0">
              <p className="text-[0.7rem] font-semibold m-0 leading-tight font-sans" style={{ color: IVORY }}>
                {f.title}
              </p>
              <p className="text-[0.58rem] m-0 leading-snug line-clamp-2 font-sans" style={{ color: `${SILVER}78` }}>
                {f.description}
              </p>
            </div>
          </motion.div>
        ))}
      </nav>
    </aside>
  );
}
