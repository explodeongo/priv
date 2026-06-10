"use client";
import { useAuth } from "./AuthProvider";
import Sidebar from "./Sidebar";
import CommandPalette from "./CommandPalette";

export default function AppShell({ children }: { children: React.ReactNode }) {
  const { user, isLoading } = useAuth();

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-screen bg-white dark:bg-slate-950">
        <div className="text-center">
          <div className="flex items-center gap-1.5 justify-center mb-3">
            {[0, 150, 300].map(d => (
              <div key={d} className="w-2.5 h-2.5 bg-red-500 rounded-full animate-bounce"
                style={{ animationDelay: `${d}ms` }} />
            ))}
          </div>
          <p className="text-gray-400 text-sm font-medium">Loading SynaptDI…</p>
        </div>
      </div>
    );
  }

  if (!user) return null;

  return (
    <div className="flex h-screen bg-white dark:bg-slate-950 overflow-hidden">
      <Sidebar />
      <div className="flex-1 min-w-0 flex flex-col overflow-hidden">
        {children}
      </div>
      <CommandPalette />
    </div>
  );
}
