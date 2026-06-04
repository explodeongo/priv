"use client";
import { createContext, useContext, useState, useEffect, ReactNode } from "react";
import { useRouter, usePathname } from "next/navigation";

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
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  updateUser: (updates: Partial<User>) => void;
  isLoading: boolean;
}

const AuthContext = createContext<AuthCtx | null>(null);

const MOCK_USERS: Record<string, { password: string; user: User }> = {
  "admin@synaptdi.com": {
    password: "admin123",
    user: { id: "1", name: "Admin User", email: "admin@synaptdi.com", role: "admin", title: "System Administrator", department: "IT Operations" },
  },
  "analyst@synaptdi.com": {
    password: "analyst123",
    user: { id: "2", name: "Sarah Chen", email: "analyst@synaptdi.com", role: "analyst", title: "Telecom Standards Analyst", department: "Architecture" },
  },
  "marcus@synaptdi.com": {
    password: "analyst123",
    user: { id: "3", name: "Marcus Johnson", email: "marcus@synaptdi.com", role: "analyst", title: "Network Standards Engineer", department: "Architecture" },
  },
  "lisa@synaptdi.com": {
    password: "viewer123",
    user: { id: "4", name: "Lisa Park", email: "lisa@synaptdi.com", role: "viewer", title: "Product Manager", department: "Product" },
  },
  "tom@synaptdi.com": {
    password: "viewer123",
    user: { id: "5", name: "Tom Wilson", email: "tom@synaptdi.com", role: "viewer", title: "Business Analyst", department: "Strategy" },
  },
};

const PUBLIC = ["/login"];

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser]         = useState<User | null>(null);
  const [isLoading, setLoading] = useState(true);
  const router   = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    try {
      const s = localStorage.getItem("synaptdi_user");
      if (s) setUser(JSON.parse(s));
    } catch {}
    setLoading(false);
  }, []);

  useEffect(() => {
    if (isLoading) return;
    const pub = PUBLIC.some(r => pathname.startsWith(r));
    if (!user && !pub) router.replace("/login");
    else if (user && pathname === "/login") router.replace("/");
  }, [user, isLoading, pathname, router]);

  const login = async (email: string, password: string) => {
    await new Promise(r => setTimeout(r, 900));
    const rec = MOCK_USERS[email.toLowerCase().trim()];
    if (!rec || rec.password !== password) throw new Error("Invalid email or password.");
    setUser(rec.user);
    localStorage.setItem("synaptdi_user", JSON.stringify(rec.user));
    localStorage.setItem("synaptdi_last_login", new Date().toISOString());
    if (!localStorage.getItem("synaptdi_joined_" + rec.user.id)) {
      localStorage.setItem("synaptdi_joined_" + rec.user.id, new Date().toISOString());
    }
  };

  const logout = () => {
    setUser(null);
    localStorage.removeItem("synaptdi_user");
    router.push("/login");
  };

  const updateUser = (updates: Partial<User>) => {
    if (!user) return;
    const next = { ...user, ...updates };
    setUser(next);
    localStorage.setItem("synaptdi_user", JSON.stringify(next));
  };

  return (
    <AuthContext.Provider value={{ user, login, logout, updateUser, isLoading }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be inside AuthProvider");
  return ctx;
}
