import { useState } from "react";
import { motion } from "framer-motion";

const NAVY = "#071426";
const GOLD = "#C8A24A";
const GOLD_DARK = "#b8943f";
const CREAM = "#F3F4F6";
const EASE = [0.22, 1, 0.36, 1];

export default function LoginFormCard({
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
  loginReady = true,
}) {
  const [showPw, setShowPw] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);

  return (
    <motion.section
      className="relative w-full shrink-0 px-5 pb-5 pt-0"
      initial={{ opacity: 0.35 }}
      animate={{ opacity: loginReady ? 1 : 0.5 }}
      transition={{ duration: 1.1, ease: EASE }}
    >
      <div
        className="absolute left-0 right-0 -top-10 h-10 pointer-events-none"
        style={{ background: `linear-gradient(180deg, transparent 0%, ${CREAM} 100%)` }}
      />

      <div
        className="relative rounded-2xl p-5"
        style={{
          background: "linear-gradient(180deg, rgba(255,255,255,0.95) 0%, rgba(243,244,246,0.98) 100%)",
          border: "1px solid rgba(7, 20, 38, 0.06)",
          boxShadow: "0 12px 40px rgba(7, 20, 38, 0.08)",
        }}
      >
      <header className="mb-4">
        <h2 className="font-sans text-lg font-bold m-0 text-slate-800">Intelligence Access Terminal</h2>
        <p className="font-sans text-sm text-slate-500 m-0 mt-1">
          Authenticate to enter the constitutional intelligence layer.
        </p>
      </header>

      <div className="flex gap-3 mb-4">
        {["login", "register"].map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setTab(t)}
            className="flex-1 py-3 rounded-xl text-sm font-bold capitalize transition-all duration-200 shadow-md"
            style={
              tab === t
                ? {
                    background: `linear-gradient(135deg, ${GOLD} 0%, ${GOLD_DARK} 100%)`,
                    color: NAVY,
                    boxShadow: `0 6px 20px ${GOLD}40`,
                  }
                : {
                    background: `linear-gradient(135deg, ${GOLD}cc 0%, ${GOLD_DARK}cc 100%)`,
                    color: NAVY,
                    opacity: 0.75,
                  }
            }
          >
            {t}
          </button>
        ))}
      </div>

      <form onSubmit={onSubmit} className="space-y-3 max-w-md">
        <div>
          <label htmlFor="username" className="block font-sans text-xs font-medium text-slate-600 mb-1.5">
            Username
          </label>
          <input
            id="username"
            type="text"
            placeholder="Enter your username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            className="w-full px-4 py-3 rounded-xl text-sm font-sans bg-white border border-slate-200 text-slate-800 placeholder:text-slate-400 focus:outline-none focus:border-amber-500/50 focus:ring-2 focus:ring-amber-500/20 transition-all"
            required
            autoComplete="username"
          />
        </div>

        <div>
          <label htmlFor="password" className="block font-sans text-xs font-medium text-slate-600 mb-1.5">
            Password
          </label>
          <div className="relative">
            <input
              id="password"
              type={showPw ? "text" : "password"}
              placeholder="Enter your password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full px-4 py-3 pr-14 rounded-xl text-sm font-sans bg-white border border-slate-200 text-slate-800 placeholder:text-slate-400 focus:outline-none focus:border-amber-500/50 focus:ring-2 focus:ring-amber-500/20 transition-all"
              required
              autoComplete={tab === "login" ? "current-password" : "new-password"}
            />
            <button
              type="button"
              onClick={() => setShowPw((s) => !s)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-xs font-sans font-medium text-slate-500 hover:text-amber-700"
              tabIndex={-1}
            >
              {showPw ? "Hide" : "Show"}
            </button>
          </div>
        </div>

        {tab === "register" && (
          <div>
            <label htmlFor="confirm" className="block font-sans text-xs font-medium text-slate-600 mb-1.5">
              Confirm password
            </label>
            <div className="relative">
              <input
                id="confirm"
                type={showConfirm ? "text" : "password"}
                placeholder="Confirm password"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                className="w-full px-4 py-3 pr-14 rounded-xl text-sm font-sans bg-white border border-slate-200 text-slate-800 focus:outline-none focus:border-amber-500/50 focus:ring-2 focus:ring-amber-500/20"
                required
              />
              <button
                type="button"
                onClick={() => setShowConfirm((s) => !s)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-xs font-sans text-slate-500"
                tabIndex={-1}
              >
                {showConfirm ? "Hide" : "Show"}
              </button>
            </div>
          </div>
        )}

        {error && (
          <p className="text-xs font-sans m-0 px-3 py-2 rounded-lg bg-red-50 text-red-700 border border-red-100">
            {error}
          </p>
        )}

        <motion.button
          type="submit"
          disabled={busy || !loginReady}
          className="w-full py-3 rounded-xl text-sm font-bold font-sans disabled:opacity-50"
          style={{
            background: `linear-gradient(135deg, ${GOLD} 0%, ${GOLD_DARK} 100%)`,
            color: NAVY,
            boxShadow: `0 8px 24px ${GOLD}35`,
          }}
          whileHover={loginReady && !busy ? { scale: 1.01, boxShadow: `0 10px 28px ${GOLD}50` } : {}}
          whileTap={{ scale: 0.99 }}
        >
          {busy ? "Please wait…" : "Enter LegalEase.AI"}
        </motion.button>
      </form>
      </div>
    </motion.section>
  );
}
