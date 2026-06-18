export const EASE = [0.22, 1, 0.36, 1];
export const GOLD = "#C8A24A";
export const GOLD_DIM = "rgba(200, 162, 74, 0.35)";
export const CHAMBER = "#0c1828";
export const CHAMBER_DEEP = "#050c16";
export const NAVY_MID = "#1a3050";
export const IVORY = "#F6F1E8";
export const SILVER = "#94a3b8";
export const FOG = "rgba(12, 24, 40, 0.85)";

/** Layer visibility 0–1 from current story phase */
export function layerOpacity(phase, startPhase, fullPhase = startPhase + 1) {
  if (phase < startPhase) return 0;
  if (phase >= fullPhase) return 1;
  return (phase - startPhase) / (fullPhase - startPhase);
}
