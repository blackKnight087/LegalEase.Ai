import { useId } from "react";

export default function LegalEaseLogo({
  size = 75,
  showText = true,
  className = "",
  align = "center",
  variant = "default",
}) {
  const uid = useId().replace(/:/g, "");
  const goldId = `gold-${uid}`;
  const glowId = `bgGlow-${uid}`;
  const goldGlowId = `goldGlow-${uid}`;
  const isGold = variant === "gold";
  const chainStroke = isGold ? `url(#${goldId})` : "#E8C878";

  return (
    <div
      className={`legalease-logo-mark ${isGold ? "legalease-logo--gold" : ""} ${className}`.trim()}
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: align === "left" ? "flex-start" : "center",
        textAlign: align === "left" ? "left" : "center",
      }}
    >
      <svg width={size} height={size} viewBox="0 0 120 120" fill="none" aria-hidden>
        <circle
          cx="60"
          cy="60"
          r="52"
          fill={isGold ? `url(#${goldGlowId})` : `url(#${glowId})`}
          opacity={isGold ? 0.22 : 0.18}
        />
        <circle
          cx="60"
          cy="60"
          r="44"
          stroke={isGold ? "rgba(212,175,55,.35)" : "rgba(59,130,246,.25)"}
          strokeWidth="1.2"
        />
        <line x1="60" y1="20" x2="60" y2="80" stroke={`url(#${goldId})`} strokeWidth="5" strokeLinecap="round" />
        <circle cx="60" cy="18" r="5" fill="#F4D58D" />
        <line x1="30" y1="35" x2="90" y2="35" stroke={`url(#${goldId})`} strokeWidth="4" strokeLinecap="round" />
        <line x1="40" y1="35" x2="32" y2="55" stroke={chainStroke} strokeWidth="2" />
        <line x1="40" y1="35" x2="48" y2="55" stroke={chainStroke} strokeWidth="2" />
        <line x1="80" y1="35" x2="72" y2="55" stroke={chainStroke} strokeWidth="2" />
        <line x1="80" y1="35" x2="88" y2="55" stroke={chainStroke} strokeWidth="2" />
        <path
          d="M24 55 C28 70, 52 70, 56 55"
          stroke={`url(#${goldId})`}
          strokeWidth="3"
          fill="rgba(212,175,55,.15)"
        />
        <path
          d="M64 55 C68 70, 92 70, 96 55"
          stroke={`url(#${goldId})`}
          strokeWidth="3"
          fill="rgba(212,175,55,.15)"
        />
        {!isGold && (
          <>
            <path d="M92 42 C108 52, 108 72, 92 84" stroke="#3B82F6" strokeWidth="2" opacity="0.8" />
            <circle cx="98" cy="46" r="2" fill="#60A5FA" />
            <circle cx="105" cy="60" r="2" fill="#60A5FA" />
            <circle cx="98" cy="75" r="2" fill="#60A5FA" />
          </>
        )}
        <path d="M45 82 H75" stroke={`url(#${goldId})`} strokeWidth="5" strokeLinecap="round" />
        <defs>
          <linearGradient id={goldId} x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="#D4AF37" />
            <stop offset="50%" stopColor="#F4D58D" />
            <stop offset="100%" stopColor="#B8860B" />
          </linearGradient>
          <radialGradient id={glowId}>
            <stop stopColor="#2563EB" />
            <stop offset="100%" stopColor="transparent" />
          </radialGradient>
          <radialGradient id={goldGlowId}>
            <stop stopColor="#F4D58D" />
            <stop offset="100%" stopColor="transparent" />
          </radialGradient>
        </defs>
      </svg>

      {showText && (
        <>
          <h1 className="legalease-logo-title">LegalEase.AI</h1>
          <p className="legalease-logo-tagline">AI-Powered Legal Intelligence</p>
        </>
      )}
    </div>
  );
}
