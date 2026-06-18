"use client";

/** Shared microphone asset (user-provided) — used across chat, drafting, and Firm Chat. */
export const MICROPHONE_ICON_SRC = "/icons/microphone.png";

type Props = {
  /** Active recording / listening */
  active?: boolean;
  /** Finalizing, transcribing, or starting */
  busy?: boolean;
  size?: number;
  className?: string;
};

/**
 * Project-standard microphone icon (capsule + stand).
 * Source: /public/icons/microphone.png
 */
export default function VoiceMicIcon({
  active = false,
  busy = false,
  size = 22,
  className = "",
}: Props) {
  const opacity = busy ? 0.55 : 1;
  const scale = active ? 1.05 : 1;

  return (
    <img
      src={MICROPHONE_ICON_SRC}
      width={size}
      height={size}
      alt=""
      aria-hidden
      className={`object-contain select-none pointer-events-none ${className}`}
      style={{
        opacity,
        transform: `scale(${scale})`,
        filter: active
          ? "brightness(0) saturate(100%) invert(24%) sepia(90%) saturate(6400%) hue-rotate(350deg) brightness(95%)"
          : "none",
        transition: "transform 0.15s ease, opacity 0.15s ease, filter 0.15s ease",
      }}
      draggable={false}
    />
  );
}
