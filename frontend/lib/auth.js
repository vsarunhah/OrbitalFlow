import { createContext, useContext, useEffect, useRef, useState } from "react";
import { useRouter } from "next/router";
import { fetchMe, clearToken, getTokenExp, refreshAccessToken } from "./api";

const REFRESH_BEFORE_EXPIRY_SEC = 5 * 60; // refresh when less than 5 min left
const CHECK_INTERVAL_MS = 60 * 1000; // check every minute

const AuthContext = createContext(null);

const PUBLIC_PATHS = ["/login", "/forgot-password", "/reset-password"];

export function AuthProvider({ children }) {
  const router = useRouter();
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  const refreshIntervalRef = useRef(null);

  useEffect(() => {
    const token =
      typeof window !== "undefined"
        ? localStorage.getItem("jt_token")
        : null;

    if (!token) {
      setLoading(false);
      if (!PUBLIC_PATHS.includes(router.pathname)) {
        router.replace("/login");
      }
      return;
    }

    fetchMe()
      .then((u) => {
        setUser(u);
        if (PUBLIC_PATHS.includes(router.pathname)) {
          router.replace("/jobs");
        }
        // Proactively refresh token before expiry so the session doesn't drop mid-use
        refreshIntervalRef.current = setInterval(() => {
          const t = typeof window !== "undefined" ? localStorage.getItem("jt_token") : null;
          if (!t) return;
          const exp = getTokenExp(t);
          if (!exp) return;
          const nowSec = Math.floor(Date.now() / 1000);
          if (exp - nowSec < REFRESH_BEFORE_EXPIRY_SEC) {
            refreshAccessToken().then((newToken) => {
              if (!newToken) {
                clearToken();
                setUser(null);
                router.replace("/login");
              }
            });
          }
        }, CHECK_INTERVAL_MS);
      })
      .catch(() => {
        clearToken();
        if (!PUBLIC_PATHS.includes(router.pathname)) {
          router.replace("/login");
        }
      })
      .finally(() => setLoading(false));

    return () => {
      if (refreshIntervalRef.current) {
        clearInterval(refreshIntervalRef.current);
        refreshIntervalRef.current = null;
      }
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  function logout() {
    if (refreshIntervalRef.current) {
      clearInterval(refreshIntervalRef.current);
      refreshIntervalRef.current = null;
    }
    clearToken();
    setUser(null);
    router.push("/login");
  }

  if (loading) {
    return <div className="loading-spinner">Loading...</div>;
  }

  if (!user && !PUBLIC_PATHS.includes(router.pathname)) {
    return <div className="loading-spinner">Redirecting...</div>;
  }

  return (
    <AuthContext.Provider value={{ user, setUser, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
