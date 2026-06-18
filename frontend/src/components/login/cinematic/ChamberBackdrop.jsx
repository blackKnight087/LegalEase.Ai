import { motion } from "framer-motion";
import { CHAMBER, CHAMBER_DEEP, GOLD, NAVY_MID, FOG } from "./chamberConstants.js";

function ArchiveShelves() {
  return (
    <svg className="absolute inset-0 w-full h-full opacity-30" aria-hidden>
      {[0, 1, 2, 3, 4].map((i) => (
        <g key={i} opacity={0.15 + i * 0.03}>
          <rect x={`${8 + i * 18}%`} y="8%" width="12%" height="3%" fill="#1e3a5f" rx="1" />
          <rect x={`${8 + i * 18}%`} y="14%" width="12%" height="2%" fill="#152a45" rx="1" />
        </g>
      ))}
    </svg>
  );
}

function VolumetricBeams() {
  return (
    <>
      <motion.div
        className="absolute top-0 left-1/2 -translate-x-1/2 w-[40%] h-full pointer-events-none"
        style={{
          background: `linear-gradient(180deg, ${GOLD}12 0%, transparent 45%)`,
          clipPath: "polygon(35% 0%, 65% 0%, 100% 100%, 0% 100%)",
        }}
        animate={{ opacity: [0.25, 0.5, 0.25] }}
        transition={{ duration: 6, repeat: Infinity, ease: "easeInOut" }}
      />
      <motion.div
        className="absolute top-0 left-[18%] w-[22%] h-[70%] pointer-events-none"
        style={{
          background: `linear-gradient(165deg, ${GOLD}08 0%, transparent 70%)`,
          transform: "skewX(-8deg)",
        }}
        animate={{ opacity: [0.1, 0.28, 0.1] }}
        transition={{ duration: 7.5, repeat: Infinity, ease: "easeInOut", delay: 0.5 }}
      />
      <motion.div
        className="absolute top-0 right-[18%] w-[22%] h-[70%] pointer-events-none"
        style={{
          background: `linear-gradient(195deg, ${GOLD}08 0%, transparent 70%)`,
          transform: "skewX(8deg)",
        }}
        animate={{ opacity: [0.1, 0.28, 0.1] }}
        transition={{ duration: 7.5, repeat: Infinity, ease: "easeInOut", delay: 1 }}
      />
    </>
  );
}

function AtmosphericFog() {
  return (
    <>
      <motion.div
        className="absolute bottom-0 left-0 right-0 h-[55%] pointer-events-none"
        style={{
          background: `linear-gradient(0deg, ${CHAMBER_DEEP} 0%, ${FOG} 40%, transparent 100%)`,
        }}
        animate={{ opacity: [0.7, 0.9, 0.7] }}
        transition={{ duration: 5, repeat: Infinity, ease: "easeInOut" }}
      />
      <motion.div
        className="absolute bottom-[20%] left-0 right-0 h-[30%] pointer-events-none"
        style={{ background: "radial-gradient(ellipse 80% 60% at 50% 100%, rgba(26,48,80,0.4) 0%, transparent 70%)" }}
        animate={{ x: [-12, 12, -12] }}
        transition={{ duration: 14, repeat: Infinity, ease: "easeInOut" }}
      />
    </>
  );
}

function Particles() {
  return (
    <div className="absolute inset-0 pointer-events-none overflow-hidden">
      {[...Array(12)].map((_, i) => (
        <motion.div
          key={i}
          className="absolute rounded-full"
          style={{
            width: i % 3 === 0 ? 2 : 1,
            height: i % 3 === 0 ? 2 : 1,
            background: GOLD,
            left: `${6 + i * 7.5}%`,
            top: `${12 + (i % 5) * 14}%`,
          }}
          animate={{ opacity: [0.08, 0.35, 0.08], y: [0, -18 - (i % 4) * 4, 0] }}
          transition={{ duration: 5 + i * 0.35, repeat: Infinity, ease: "easeInOut" }}
        />
      ))}
    </div>
  );
}

export default function ChamberBackdrop({ archiveOpacity = 1 }) {
  return (
    <>
      <div
        className="absolute inset-0"
        style={{
          background: `radial-gradient(ellipse 75% 85% at 50% 95%, ${NAVY_MID} 0%, ${CHAMBER} 50%, ${CHAMBER_DEEP} 100%)`,
        }}
      />
      <motion.div
        className="absolute inset-0"
        style={{ opacity: archiveOpacity }}
        initial={false}
      >
        <ArchiveShelves />
      </motion.div>
      <VolumetricBeams />
      <motion.div
        className="absolute inset-0"
        animate={{ opacity: [0.3, 0.55, 0.3] }}
        transition={{ duration: 5.5, repeat: Infinity, ease: "easeInOut" }}
        style={{
          background: `radial-gradient(ellipse at 50% 28%, ${GOLD}16 0%, transparent 52%)`,
        }}
      />
      <AtmosphericFog />
      <Particles />
      {/* Constitutional axis — vertical gold line behind logo mount */}
      <motion.div
        className="absolute top-[12%] bottom-[28%] left-1/2 w-px -translate-x-1/2 pointer-events-none"
        style={{
          background: `linear-gradient(180deg, transparent, ${GOLD}35, ${GOLD}20, transparent)`,
        }}
        animate={{ opacity: [0.2, 0.45, 0.2] }}
        transition={{ duration: 4, repeat: Infinity, ease: "easeInOut" }}
      />
    </>
  );
}
