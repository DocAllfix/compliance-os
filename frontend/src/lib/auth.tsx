import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import { auth, type User } from './api';

interface AuthState {
  user: User | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!auth.hasToken()) {
      setLoading(false);
      return;
    }
    auth
      .me()
      .then(setUser)
      .catch(() => auth.clearToken())
      .finally(() => setLoading(false));
  }, []);

  const login = async (username: string, password: string) => {
    const { token, user: u } = await auth.login(username, password);
    auth.setToken(token);
    setUser(u);
  };

  const logout = async () => {
    try {
      await auth.logout();
    } catch {
      // ignore
    }
    auth.clearToken();
    setUser(null);
  };

  return <AuthContext.Provider value={{ user, loading, login, logout }}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>');
  return ctx;
}
