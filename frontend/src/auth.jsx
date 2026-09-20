import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { auth, clearTokens, ensureAccessToken, hasSession } from './api';
import { disconnectSocket } from './socket';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  const refreshUser = useCallback(async () => {
    try {
      setUser(await auth.me());
    } catch {
      clearTokens();
      setUser(null);
    }
  }, []);

  useEffect(() => {
    (async () => {
      if (hasSession()) {
        try {
          await ensureAccessToken();
          await refreshUser();
        } catch {
          clearTokens();
        }
      }
      setLoading(false);
    })();
  }, [refreshUser]);

  const value = useMemo(
    () => ({
      user,
      loading,
      async login(email, password) {
        await auth.login(email, password);
        await refreshUser();
      },
      async register(name, email, password) {
        await auth.register(name, email, password);
        await auth.login(email, password);
        await refreshUser();
      },
      async logout() {
        disconnectSocket();
        await auth.logout();
        setUser(null);
      },
      refreshUser,
    }),
    [user, loading, refreshUser],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider');
  return ctx;
}
