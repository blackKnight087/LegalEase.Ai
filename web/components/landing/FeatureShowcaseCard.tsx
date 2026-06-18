"use client";

import { useCallback, useEffect, useRef, useState } from "react";

const ACCENTS = ["#eab308", "#2563eb", "#7c3aed", "#059669", "#d97706", "#dc2626"];

type Props = {
  icon: string;
  title: string;
  description: string;
  index: number;
};

export default function FeatureShowcaseCard({ icon, title, description, index }: Props) {
  const cardRef = useRef<HTMLDivElement>(null);
  const [transform, setTransform] = useState("");
  const [hovered, setHovered] = useState(false);
  const [reduceMotion, setReduceMotion] = useState(false);

  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setReduceMotion(mq.matches);
    update();
    mq.addEventListener("change", update);
    return () => mq.removeEventListener("change", update);
  }, []);

  const accent = ACCENTS[index % ACCENTS.length];

  const handleMove = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      if (reduceMotion) return;
      const el = cardRef.current;
      if (!el) return;
      const rect = el.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;
      const cx = rect.width / 2;
      const cy = rect.height / 2;
      const rotateY = ((x - cx) / cx) * 6;
      const rotateX = ((cy - y) / cy) * 6;
      setTransform(
        `perspective(800px) rotateX(${rotateX.toFixed(2)}deg) rotateY(${rotateY.toFixed(2)}deg) translateZ(10px) scale(1.02)`
      );
    },
    [reduceMotion]
  );

  const handleLeave = useCallback(() => {
    setTransform("");
    setHovered(false);
  }, []);

  return (
    <article
      className="landing-feature-wrap"
      style={
        {
          "--i": index,
          "--accent": accent,
        } as React.CSSProperties
      }
    >
      <div
        ref={cardRef}
        className={`landing-feature-card${hovered ? " is-hovered" : ""}`}
        style={transform ? { transform } : undefined}
        onMouseMove={handleMove}
        onMouseLeave={handleLeave}
        onMouseEnter={() => setHovered(true)}
      >
        <div className="landing-feature-card-inner">
          <div className="landing-feature-icon">{icon}</div>
          <h3 className="landing-feature-title">{title}</h3>
          <p className="landing-feature-desc">{description}</p>
        </div>
        <div className="landing-feature-shine" aria-hidden />
      </div>
    </article>
  );
}
