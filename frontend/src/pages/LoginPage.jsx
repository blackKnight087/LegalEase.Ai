import { useState } from "react";
import { Navigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext.jsx";
import LandingSidebar from "../components/landing/LandingSidebar.jsx";
import LandingMain from "../components/landing/LandingMain.jsx";

/** Classic dynamic landing — sidebar auth + 3×3 feature grid */
export default function LoginPage() {
  const { user, loading, login, register } = useAuth();
  const [tab, setTab] = useState("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  if (!loading && user) return <Navigate to="/" replace />;

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      if (tab === "login") await login(username, password);
      else await register(username, password, confirm);
    } catch (err) {
      const msg = err.message || "Authentication failed";
      setError(
        msg.includes("API not responding")
          ? msg
          : msg === "Invalid username or password"
            ? msg
            : `${msg}. If this persists, run .\\stop_saas.ps1 then .\\run_saas.ps1`
      );
    } finally {
      setBusy(false);
    }
  };

  if (loading) {
    return (
      <div className="landing-page items-center justify-center">
        <div className="w-9 h-9 border-2 border-blue-400/30 border-t-blue-600 rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="landing-page">
      <LandingSidebar
        tab={tab}
        setTab={setTab}
        username={username}
        setUsername={setUsername}
        password={password}
        setPassword={setPassword}
        confirm={confirm}
        setConfirm={setConfirm}
        error={error}
        busy={busy}
        onSubmit={submit}
      />
      <LandingMain setTab={setTab} />
    </div>
  );
}
