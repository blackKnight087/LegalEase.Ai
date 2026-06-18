import { useState } from "react";
import { motion } from "framer-motion";

const LOGO_SRC = "/legalease_scales_logo.png";

/** Official 3D LegalEase scales logo (gold + AI blue circuitry) */
export default function BrandLogo({ className = "w-11 h-11", alt = "LegalEase.AI", animate = false }) {
  const [src, setSrc] = useState(LOGO_SRC);

  const img = (
    <img
      src={src}
      alt={alt}
      className={`object-contain shrink-0 rounded-lg ${className}`}
      onError={() => setSrc("/scales-logo.svg")}
    />
  );

  if (!animate) return img;

  return (
    <motion.div
      animate={{ scale: [1, 1.03, 1] }}
      transition={{ duration: 4.5, repeat: Infinity, ease: "easeInOut" }}
      style={{
        filter:
          "drop-shadow(0 0 20px rgba(245, 158, 11, 0.35)) drop-shadow(0 0 28px rgba(59, 130, 246, 0.25))",
      }}
    >
      {img}
    </motion.div>
  );
}
