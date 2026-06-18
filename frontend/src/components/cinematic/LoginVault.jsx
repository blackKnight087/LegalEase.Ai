const NAVY = "#071426";
const GOLD = "#C8A24A";
const IVORY = "#F6F1E8";
const SILVER = "#B8C0CC";

export default function LoginVault({
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
  return (
    <div
      className="rounded-2xl p-7 shadow-2xl"
      style={{
        background: `linear-gradient(165deg, rgba(7, 20, 38, 0.75) 0%, rgba(12, 32, 58, 0.55) 100%)`,
        backdropFilter: "blur(20px)",
        WebkitBackdropFilter: "blur(20px)",
        border: `1px solid ${GOLD}33`,
        boxShadow: `0 24px 80px rgba(0,0,0,0.5), 0 0 40px ${GOLD}11`,
      }}
    >
      <div className="flex gap-2 mb-5">
        {["login", "register"].map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setTab(t)}
            className="flex-1 py-2 rounded-lg text-sm font-semibold capitalize transition-all duration-300"
            style={
              tab === t
                ? {
                    background: `linear-gradient(135deg, ${GOLD} 0%, #a8863e 100%)`,
                    color: NAVY,
                    border: `1px solid ${GOLD}`,
                  }
                : {
                    background: "rgba(255,255,255,0.04)",
                    color: SILVER,
                    border: "1px solid rgba(255,255,255,0.1)",
                  }
            }
          >
            {t}
          </button>
        ))}
      </div>

      <form onSubmit={onSubmit} className="space-y-3">
        <input
          type="text"
          placeholder="Username"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          className="w-full px-4 py-3 rounded-xl text-sm transition-all focus:outline-none"
          style={{
            background: "rgba(246, 241, 232, 0.08)",
            border: `1px solid ${SILVER}33`,
            color: IVORY,
          }}
          required
          autoComplete="username"
        />
        <input
          type="password"
          placeholder="Password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="w-full px-4 py-3 rounded-xl text-sm transition-all focus:outline-none"
          style={{
            background: "rgba(246, 241, 232, 0.08)",
            border: `1px solid ${SILVER}33`,
            color: IVORY,
          }}
          required
          autoComplete={tab === "login" ? "current-password" : "new-password"}
        />
        {tab === "register" && (
          <input
            type="password"
            placeholder="Confirm password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            className="w-full px-4 py-3 rounded-xl text-sm"
            style={{
              background: "rgba(246, 241, 232, 0.08)",
              border: `1px solid ${SILVER}33`,
              color: IVORY,
            }}
            required
          />
        )}
        {error && (
          <p
            className="text-sm px-3 py-2 rounded-lg m-0"
            style={{ color: "#fca5a5", background: "rgba(127,29,29,0.35)" }}
          >
            {error}
          </p>
        )}
        <button
          type="submit"
          disabled={busy}
          className="w-full py-3 rounded-xl font-semibold text-sm transition-all disabled:opacity-50"
          style={{
            background: `linear-gradient(135deg, ${GOLD} 0%, #a8863e 100%)`,
            color: NAVY,
            boxShadow: `0 8px 24px ${GOLD}33`,
          }}
        >
          {busy ? "Please wait…" : "Sign In"}
        </button>
      </form>
    </div>
  );
}
