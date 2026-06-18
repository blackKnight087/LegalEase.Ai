import { useState } from "react";
import { motion } from "framer-motion";
import SidebarBrand from "./SidebarBrand.jsx";

const EASE = [0.22, 1, 0.36, 1];

export default function LandingSidebar({
  tab,
  setTab,
  username,
  setUsername,
  password,
  setPassword,
  confirm,
  setConfirm,
  error,
  busy,
  onSubmit,
}) {
  const [showPw, setShowPw] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);

  return (
    <aside className="landing-sidebar">
      <motion.div
        className="landing-sidebar-brand"
        initial={{ opacity: 0, y: -8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: EASE }}
      >
        <SidebarBrand />
      </motion.div>

      <div className="landing-auth-section">
        <h2 className="landing-auth-heading">Authentication</h2>

        <div className="landing-auth-nav">
          <button
            type="button"
            className={`landing-auth-link ${tab === "login" ? "active" : ""}`}
            onClick={() => setTab("login")}
          >
            <span className="landing-auth-icon" aria-hidden>
              🔒
            </span>
            Login
          </button>
          <button
            type="button"
            className={`landing-auth-link ${tab === "register" ? "active" : ""}`}
            onClick={() => setTab("register")}
          >
            <span className="landing-auth-icon" aria-hidden>
              📄
            </span>
            Register
          </button>
        </div>

        <form className="landing-auth-form" onSubmit={onSubmit}>
          <label htmlFor="land-user">Username</label>
          <input
            id="land-user"
            type="text"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            placeholder="Username"
            required
            autoComplete="username"
          />

          <label htmlFor="land-pass">Password</label>
          <div className="landing-password-wrap">
            <input
              id="land-pass"
              type={showPw ? "text" : "password"}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Password"
              required
              autoComplete={tab === "login" ? "current-password" : "new-password"}
            />
            <button
              type="button"
              className="landing-password-eye"
              onClick={() => setShowPw((v) => !v)}
              aria-label={showPw ? "Hide password" : "Show password"}
              tabIndex={-1}
            >
              {showPw ? "🙈" : "👁"}
            </button>
          </div>

          {tab === "register" && (
            <>
              <label htmlFor="land-confirm">Confirm password</label>
              <div className="landing-password-wrap">
                <input
                  id="land-confirm"
                  type={showConfirm ? "text" : "password"}
                  value={confirm}
                  onChange={(e) => setConfirm(e.target.value)}
                  placeholder="Confirm password"
                  required
                />
                <button
                  type="button"
                  className="landing-password-eye"
                  onClick={() => setShowConfirm((v) => !v)}
                  tabIndex={-1}
                >
                  {showConfirm ? "🙈" : "👁"}
                </button>
              </div>
            </>
          )}

          {error && <p className="landing-auth-error">{error}</p>}

          <button type="submit" className="landing-auth-submit" disabled={busy}>
            {busy ? "Please wait…" : tab === "login" ? "Login" : "Register"}
          </button>
        </form>
      </div>
    </aside>
  );
}
