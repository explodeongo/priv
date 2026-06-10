import type { Metadata } from "next";
import "./globals.css";
import { AuthProvider } from "./components/AuthProvider";
import { ToastProvider } from "./components/Toast";
import { BrandingProvider } from "./components/BrandingContext";
import { ConversationProvider } from "./components/ConversationContext";
import { ThemeProvider } from "./components/ThemeContext";

// Runs before paint so the correct theme is applied with no flash of the wrong one.
const themeScript = `(function(){try{var t=localStorage.getItem('synaptdi_theme')||'system';var d=t==='dark'||(t==='system'&&window.matchMedia('(prefers-color-scheme: dark)').matches);if(d)document.documentElement.classList.add('dark');}catch(e){}})();`;

export const metadata: Metadata = {
  title: "SynaptDI",
  description: "SynaptDI — Enterprise domains at your fingertips",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body className="antialiased">
        <ThemeProvider>
          <AuthProvider>
            <BrandingProvider>
              <ConversationProvider>
                <ToastProvider>
                  {children}
                </ToastProvider>
              </ConversationProvider>
            </BrandingProvider>
          </AuthProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
