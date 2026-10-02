import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api, setAuthToken } from "../api/rest";
import { useTradingStore } from "./store";
import type { AccountInfo } from "../types";

interface AuthState {
  token: string | null;
  account: AccountInfo | null;
  ready: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthState | null>(null);
const STORAGE_KEY = "jmi-crypto.token";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(() => sessionStorage.getItem(STORAGE_KEY));
  const [account, setAccount] = useState<AccountInfo | null>(null);
  const [ready, setReady] = useState(false);

  const logout = useCallback(() => {
    setAuthToken(null);
    sessionStorage.removeItem(STORAGE_KEY);
    setToken(null);
    setAccount(null);
    useTradingStore.getState().reset();
  }, []);

  const login = useCallback(async (username: string, password: string) => {
    const res = await api.login(username, password);
    setAuthToken(res.access_token);
    sessionStorage.setItem(STORAGE_KEY, res.access_token);
    // Fetch the account first: it carries can_view_risk, which decides what
    // the WebSocket subscribes to, so the page should mount with it known.
    const me = await api.me();
    setAccount(me);
    setToken(res.access_token);
  }, []);

  // Rehydrate account info if a token survived from a previous page load.
  useEffect(() => {
    if (!token) {
      setReady(true);
      return;
    }
    setAuthToken(token);
    api
      .me()
      .then(setAccount)
      .catch(() => logout())
      .finally(() => setReady(true));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return <AuthContext.Provider value={{ token, account, ready, login, logout }}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
