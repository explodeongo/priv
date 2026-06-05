"use client";
import { createContext, useContext, useState, useEffect, ReactNode } from "react";
import { useRouter, usePathname } from "next/navigation";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface User {
  id: string;
  name: string;
  email: string;
  role: "admin" | "analyst" | "viewer";
  title?: string;
  department?: string;
  avatar?: string;   // base64 data-URL of the uploaded profile photo
}

interface AuthCtx {
  user: User | null;
  token: string | null;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  updateUser: (updates: Partial<User>) => void;
  isLoading: boolean;
}

const AuthContext = createContext<AuthCtx | null>(null);
const PUBLIC = ["/login"];

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser]         = useState<User | null>(null);
  const [token, setToken]       = useState<string | null>(null);
  const [isLoading, setLoading] = useState(true);
  const router   = useRouter();
  const pathname = usePathname();

  // Restore the session from a stored token by asking the backend who we are.
  useEffect(() => {
    let t: string | null = null;
    try { t = localStorage.getItem("synaptdi_token"); } catch {}
    if (!t) { setLoading(false); return; }
    setToken(t);
    fetch(`${API}/auth/me`, { headers: { Authorization: `Bearer ${t}` } })
      .then(r => (r.ok ? r.json() : Promise.reject()))
      .then(d => {
        let avatar: string | undefined;
        try { avatar = localStorage.getItem("synaptdi_avatar_" + d.user.id) || undefined; } catch {}
        setUser({ ...d.user, avatar });
      })
      .catch(() => { try { localStorage.removeItem("synaptdi_token"); } catch {} setToken(null); })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (isLoading) return;
    const pub = PUBLIC.some(r => pathname.startsWith(r));
    if (!user && !pub) router.replace("/login");
    else if (user && pathname === "/login") router.replace("/");
  }, [user, isLoading, pathname, router]);

  const login = async (email: string, password: string) => {
    const res = await fetch(`${API}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: email.trim(), password }),
    });
    if (!res.ok) {
      throw new Error(res.status === 401 ? "Invalid email or password." : `Login failed (${res.status}).`);
    }
    const data = await res.json();
    setUser(data.user);
    setToken(data.token);
    try {
      localStorage.setItem("synaptdi_token", data.token);
      localStorage.setItem("synaptdi_last_login", new Date().toISOString());
      if (!localStorage.getItem("synaptdi_joined_" + data.user.id)) {
        localStorage.setItem("synaptdi_joined_" + data.user.id, new Date().toISOString());
      }
    } catch {}
  };

  const logout = () => {
    setUser(null);
    setToken(null);
    try { localStorage.removeItem("synaptdi_token"); } catch {}
    router.push("/login");
  };

  // Local-only profile tweaks (e.g. avatar); authoritative fields come from /auth/me.
  const updateUser = (updates: Partial<User>) => {
    if (!user) return;
    setUser({ ...user, ...updates });
  };

  return (
    <AuthContext.Provider value={{ user, token, login, logout, updateUser, isLoading }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be inside AuthProvider");
  return ctx;
}
