import React, { createContext, useContext, useEffect, useState, useCallback, ReactNode } from "react";
import { Platform } from "react-native";
import * as WebBrowser from "expo-web-browser";
import * as Linking from "expo-linking";

import { apiFetch, setToken, clearToken, getToken } from "@/src/api/client";

export type User = {
  user_id: string;
  email: string;
  name?: string | null;
  picture?: string | null;
  providers: string[];
  business_profile?: {
    business_name?: string;
    business_type?: string;
    region?: string;
    main_products?: string;
    role?: string;
    language?: "fr" | "en";
  } | null;
};

type AuthCtx = {
  user: User | null;
  loading: boolean;
  signup: (email: string, password: string, name?: string) => Promise<void>;
  login: (email: string, password: string) => Promise<void>;
  googleLogin: () => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
  updateProfile: (patch: Partial<NonNullable<User["business_profile"]>>) => Promise<void>;
};

const Ctx = createContext<AuthCtx | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    const tok = await getToken();
    if (!tok) {
      setUser(null);
      return;
    }
    try {
      const u = await apiFetch<User>("/auth/me");
      setUser(u);
    } catch {
      await clearToken();
      setUser(null);
    }
  }, []);

  // On mount: check web session_id in URL, then check stored token
  useEffect(() => {
    (async () => {
      console.log("[Auth] mount: starting");
      try {
        if (Platform.OS === "web" && typeof window !== "undefined") {
          const hash = window.location.hash || "";
          const search = window.location.search || "";
          const m = hash.match(/session_id=([^&]+)/) || search.match(/session_id=([^&]+)/);
          if (m && m[1]) {
            console.log("[Auth] found session_id in URL");
            await handleGoogleSessionId(decodeURIComponent(m[1]));
            window.history.replaceState(null, "", window.location.pathname);
          }
        }
        console.log("[Auth] calling refresh()");
        await refresh();
        console.log("[Auth] refresh done");
      } catch (e) {
        console.warn("[Auth] mount error", e);
      } finally {
        console.log("[Auth] setLoading(false)");
        setLoading(false);
      }
    })();
  }, [refresh]);

  const handleGoogleSessionId = async (sessionId: string) => {
    const data = await apiFetch<{ access_token: string; user: User }>(
      "/auth/google/session",
      {
        method: "POST",
        body: JSON.stringify({ session_token: sessionId }),
        auth: false,
      }
    );
    await setToken(data.access_token);
    setUser(data.user);
  };

  const signup = async (email: string, password: string, name?: string) => {
    const data = await apiFetch<{ access_token: string; user: User }>(
      "/auth/signup",
      {
        method: "POST",
        body: JSON.stringify({ email, password, name }),
        auth: false,
      }
    );
    await setToken(data.access_token);
    setUser(data.user);
  };

  const login = async (email: string, password: string) => {
    const data = await apiFetch<{ access_token: string; user: User }>(
      "/auth/login",
      {
        method: "POST",
        body: JSON.stringify({ email, password }),
        auth: false,
      }
    );
    await setToken(data.access_token);
    setUser(data.user);
  };

  const googleLogin = async () => {
    if (Platform.OS === "web" && typeof window !== "undefined") {
      const redirect = window.location.origin + "/";
      const authUrl = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirect)}`;
      window.location.href = authUrl;
      return;
    }
    const redirectUrl = Linking.createURL("auth");
    const authUrl = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;
    const result = await WebBrowser.openAuthSessionAsync(authUrl, redirectUrl);
    if (result.type !== "success" || !result.url) return;

    const url = result.url;
    const hashMatch = url.match(/#session_id=([^&]+)/);
    const queryMatch = url.match(/[?&]session_id=([^&]+)/);
    const sessionId = (hashMatch && hashMatch[1]) || (queryMatch && queryMatch[1]);
    if (sessionId) {
      await handleGoogleSessionId(decodeURIComponent(sessionId));
    }
  };

  const logout = async () => {
    try {
      await apiFetch("/auth/logout", { method: "POST" });
    } catch {
      /* ignore */
    }
    await clearToken();
    setUser(null);
  };

  const updateProfile = async (patch: Partial<NonNullable<User["business_profile"]>>) => {
    const u = await apiFetch<User>("/profile", {
      method: "PUT",
      body: JSON.stringify(patch),
    });
    setUser(u);
  };

  return (
    <Ctx.Provider
      value={{ user, loading, signup, login, googleLogin, logout, refresh, updateProfile }}
    >
      {children}
    </Ctx.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
