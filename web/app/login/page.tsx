"use client";

import Link from "next/link";
import { FormEvent, Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/components/providers/AuthProvider";
import { useApiConnection } from "@/components/providers/ApiConnectionProvider";
import { register as apiRegister } from "@/lib/api";
import * as api from "@/lib/api";
import FeatureShowcaseCard from "@/components/landing/FeatureShowcaseCard";
import { LANDING_FEATURES } from "@/data/landingFeatures";
import "../landing.css";

function LoginPageInner() {
  const { login, user, loading } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const rawNext = searchParams.get("next");
  const nextPath = !rawNext || rawNext === "/" ? "/dashboard" : rawNext;
  const [tab, setTab] = useState<"login" | "register">("login");
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [acceptTerms, setAcceptTerms] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [ssoEnabled, setSsoEnabled] = useState(false);
  const { apiOnline, checking, connectionChecked, refreshConnection } =
    useApiConnection();

  useEffect(() => {
    api.fetchSsoStatus().then((s) => setSsoEnabled(Boolean(s.enabled))).catch(() => {});
  }, []);

  useEffect(() => {
    if (!loading && user) {
      router.replace(nextPath.startsWith("/") ? nextPath : "/");
    }
  }, [loading, user, router, nextPath]);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      const online = await refreshConnection();
      if (!online) {
        setError(
          typeof window !== "undefined" &&
            (window.location.hostname === "localhost" ||
              window.location.hostname === "127.0.0.1")
            ? "Backend is not running. Open a new PowerShell window in the project folder, run .\\run_backend.ps1, wait until you see 'Uvicorn running', then click Retry above."
            : "Cannot reach the server. Check your internet connection and try again, or click Retry above."
        );
        return;
      }
      if (tab === "login") {
        await login(username, password, nextPath);
      } else {
        if (!acceptTerms) {
          setError("Please accept the Terms of Service and Privacy Policy");
          return;
        }
        const res = await apiRegister(username, password, confirm, true, email.trim());
        localStorage.setItem("legalease_token", res.token);
        await login(username, password);
        router.replace("/onboarding");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Authentication failed");
    } finally {
      setBusy(false);
    }
  };

  const onSsoLogin = async () => {
    setError("");
    setBusy(true);
    try {
      const st = await api.fetchSsoStatus();
      if (st.dev_mock) {
        const email = window.prompt("Enterprise SSO email (dev mock):");
        if (!email) return;
        const res = await api.ssoCallback({ email, name: email.split("@")[0] });
        localStorage.setItem("legalease_token", res.token);
        document.cookie = `legalease_token=${encodeURIComponent(res.token)}; path=/; max-age=${7 * 24 * 60 * 60}; SameSite=Lax`;
        router.replace(nextPath.startsWith("/") ? nextPath : "/");
        return;
      }
      const { authorize_url } = await api.ssoLoginStart();
      window.location.href = authorize_url;
    } catch (err) {
      setError(err instanceof Error ? err.message : "SSO unavailable");
    } finally {
      setBusy(false);
    }
  };

  if (loading || user) {
    return (
      <div className="landing-page items-center justify-center">
        <div className="w-9 h-9 border-2 border-blue-400/30 border-t-blue-600 rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="landing-page">
      <aside className="landing-sidebar">
        <div className="landing-sidebar-brand">
          <div className="font-serif text-lg font-bold text-white">⚖️ LegalEase.AI</div>
          <p className="text-[0.68rem] text-slate-400 mt-1">AI-Powered Legal Intelligence</p>
        </div>
        <div className="landing-auth-section">
          <h2 className="landing-auth-heading">Authentication</h2>
          <div className="landing-auth-nav">
            <button
              type="button"
              className={`landing-auth-link ${tab === "login" ? "active" : ""}`}
              onClick={() => setTab("login")}
            >
              <span>🔒</span> Login
            </button>
            <button
              type="button"
              className={`landing-auth-link ${tab === "register" ? "active" : ""}`}
              onClick={() => setTab("register")}
            >
              <span>📄</span> Register
            </button>
          </div>
          <form className="landing-auth-form" onSubmit={onSubmit}>
            <label htmlFor="user">Username</label>
            <input
              id="user"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
              autoComplete="username"
            />
            <label htmlFor="pass">Password</label>
            <input
              id="pass"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              autoComplete={tab === "login" ? "current-password" : "new-password"}
            />
            {tab === "register" && (
              <>
                <label htmlFor="email">Email (for password reset)</label>
                <input
                  id="email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  autoComplete="email"
                  placeholder="you@gmail.com"
                />
                <label htmlFor="confirm">Confirm password</label>
                <input
                  id="confirm"
                  type="password"
                  value={confirm}
                  onChange={(e) => setConfirm(e.target.value)}
                  required
                />
                <label className="flex items-start gap-2 text-[0.72rem] text-slate-400 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={acceptTerms}
                    onChange={(e) => setAcceptTerms(e.target.checked)}
                    className="mt-0.5"
                  />
                  <span>
                    I agree to the{" "}
                    <Link href="/legal/terms" className="underline text-slate-300" target="_blank">
                      Terms of Service
                    </Link>{" "}
                    and{" "}
                    <Link href="/legal/privacy" className="underline text-slate-300" target="_blank">
                      Privacy Policy
                    </Link>
                  </span>
                </label>
              </>
            )}
            {tab === "login" && (
              <Link href="/forgot-password" className="text-[0.72rem] text-slate-400 hover:underline">
                Forgot password?
              </Link>
            )}
            {!connectionChecked || checking ? (
              <p className="text-[0.7rem] text-slate-400">Checking backend…</p>
            ) : apiOnline ? (
              <p className="landing-api-ok">API connected — you can log in</p>
            ) : (
              <p className="landing-api-err">
                {typeof window !== "undefined" &&
                (window.location.hostname === "localhost" ||
                  window.location.hostname === "127.0.0.1") ? (
                  <>
                    Backend not reachable. Terminal 1:{" "}
                    <code className="text-[0.85em]">.\run_backend.ps1</code> (wait for
                    Uvicorn). Terminal 2:{" "}
                    <code className="text-[0.85em]">.\run_web.ps1</code> — then{" "}
                  </>
                ) : (
                  <>Server not reachable — check your connection, then </>
                )}
                <button
                  type="button"
                  className="underline ml-1"
                  onClick={() => void refreshConnection()}
                >
                  Retry
                </button>
              </p>
            )}
            {error && <p className="landing-api-err">{error}</p>}
            <button type="submit" className="landing-auth-submit" disabled={busy}>
              {busy ? "Please wait…" : tab === "login" ? "Login" : "Register"}
            </button>
            {tab === "login" && ssoEnabled && (
              <button
                type="button"
                className="w-full mt-2 py-2.5 rounded-lg border border-slate-500 text-slate-200 text-sm hover:bg-slate-800/50"
                disabled={busy}
                onClick={() => void onSsoLogin()}
              >
                Sign in with SSO (Enterprise)
              </button>
            )}
          </form>
        </div>
      </aside>

      <div className="landing-main">
        <div className="landing-main-inner">
          <div className="landing-welcome">
            <span className="text-3xl">⚖️</span>
            <h1>Welcome to LegalEase.AI</h1>
          </div>
          <p className="landing-subtitle">India&apos;s Most Advanced AI-Powered Legal Platform</p>
          <div className="landing-tool-grid">
            {LANDING_FEATURES.map((f, i) => (
              <FeatureShowcaseCard
                key={f.title}
                icon={f.icon}
                title={f.title}
                description={f.description}
                index={i}
              />
            ))}
          </div>
        </div>
        <div className="landing-banner">
          Please{" "}
          <button type="button" className="landing-banner-link" onClick={() => setTab("login")}>
            Login
          </button>{" "}
          or{" "}
          <button type="button" className="landing-banner-link" onClick={() => setTab("register")}>
            Register
          </button>{" "}
          to access the platform.
        </div>
      </div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense
      fallback={
        <div className="landing-page items-center justify-center">
          <div className="w-9 h-9 border-2 border-blue-400/30 border-t-blue-600 rounded-full animate-spin" />
        </div>
      }
    >
      <LoginPageInner />
    </Suspense>
  );
}
