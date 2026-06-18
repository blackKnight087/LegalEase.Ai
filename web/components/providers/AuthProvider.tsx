"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  ReactNode,
} from "react";
import { useRouter } from "next/navigation";
import { getMe, login as apiLogin } from "@/lib/api";
import { identifyUser, ProductEvents, resetAnalytics, trackEvent } from "@/lib/productAnalytics";

export type User = {
  id: string;
  username: string;
  membership: string;
  role?: string;
};

type AuthCtx = {
  user: User | null;
  loading: boolean;
  login: (u: string, p: string, redirectTo?: string) => Promise<void>;
  logout: () => void;
  setUser: (u: User | null) => void;
  refreshUser: () => Promise<void>;
};

const AuthContext = createContext<AuthCtx | null>(null);

function syncTokenCookie(token: string | null) {
  if (typeof document === "undefined") return;
  if (token) {
    const maxAge = 7 * 24 * 60 * 60;
    document.cookie = `legalease_token=${encodeURIComponent(token)}; path=/; max-age=${maxAge}; SameSite=Lax`;
  } else {
    document.cookie = "legalease_token=; path=/; max-age=0";
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const router = useRouter();

  useEffect(() => {
    const token = localStorage.getItem("legalease_token");
    if (!token) {
      syncTokenCookie(null);
      setLoading(false);
      return;
    }
    syncTokenCookie(token);
    let cancelled = false;
    const failSafe = window.setTimeout(() => {
      if (cancelled) return;
      localStorage.removeItem("legalease_token");
      syncTokenCookie(null);
      setUser(null);
      setLoading(false);
    }, 15000);
    getMe()
      .then((r) => {
        if (!cancelled) {
          const u = r.user as User;
          setUser(u);
          identifyUser(u.id, {
            username: u.username,
            membership: u.membership,
            role: u.role,
          });
        }
      })
      .catch(() => {
        localStorage.removeItem("legalease_token");
        syncTokenCookie(null);
      })
      .finally(() => {
        cancelled = true;
        window.clearTimeout(failSafe);
        setLoading(false);
      });
    return () => {
      cancelled = true;
      window.clearTimeout(failSafe);
    };
  }, []);

  const login = useCallback(async (username: string, password: string, redirectTo?: string) => {
    const res = await apiLogin(username, password);
    localStorage.setItem("legalease_token", res.token);
    syncTokenCookie(res.token);
    const loggedIn = res.user as User;
    setUser(loggedIn);
    identifyUser(String(loggedIn.id), {
      username: loggedIn.username,
      membership: loggedIn.membership,
      role: loggedIn.role,
    });
    trackEvent(ProductEvents.login, { membership: loggedIn.membership });
    const dest =
      redirectTo && redirectTo.startsWith("/") && redirectTo !== "/"
        ? redirectTo
        : "/dashboard";
    router.replace(dest);
  }, [router]);

  const logout = useCallback(() => {
    trackEvent(ProductEvents.logout);
    resetAnalytics();
    localStorage.removeItem("legalease_token");
    syncTokenCookie(null);
    setUser(null);
    router.push("/login");
  }, [router]);

  const refreshUser = useCallback(async () => {
    const r = await getMe();
    setUser(r.user as User);
  }, []);

  return (
    <AuthContext.Provider
      value={{ user, loading, login, logout, setUser, refreshUser }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth outside AuthProvider");
  return ctx;
}
