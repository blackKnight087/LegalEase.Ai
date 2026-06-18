import { motion } from "framer-motion";
import { LANDING_FEATURES } from "../../data/landingFeatures.js";

const EASE = [0.22, 1, 0.36, 1];

export default function LandingMain({ setTab }) {
  return (
    <div className="landing-main">
      <div className="landing-main-inner">
        <motion.div
          className="landing-welcome"
          initial={{ opacity: 0, x: 16 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.6, ease: EASE }}
        >
          <span className="landing-welcome-scales" aria-hidden>
            ⚖️
          </span>
          <h1>Welcome to LegalEase.AI</h1>
        </motion.div>

        <motion.p
          className="landing-subtitle"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.6, delay: 0.1, ease: EASE }}
        >
          India&apos;s Most Advanced AI-Powered Legal Platform
        </motion.p>

        <div className="landing-tool-grid">
          {LANDING_FEATURES.map((f, i) => (
            <motion.article
              key={f.title}
              className="landing-feature-card"
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.45, delay: 0.06 * i, ease: EASE }}
            >
              <div className="landing-feature-icon" aria-hidden>
                {f.icon}
              </div>
              <h3 className="landing-feature-title">{f.title}</h3>
              <p className="landing-feature-desc">{f.description}</p>
            </motion.article>
          ))}
        </div>
      </div>

      <motion.div
        className="landing-banner"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.5, delay: 0.4, ease: EASE }}
      >
        <span aria-hidden>👉</span> Please{" "}
        <button type="button" className="landing-banner-link" onClick={() => setTab("login")}>
          Login
        </button>{" "}
        or{" "}
        <button type="button" className="landing-banner-link" onClick={() => setTab("register")}>
          Register
        </button>{" "}
        to access all features.
      </motion.div>
    </div>
  );
}
