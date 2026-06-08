import type { Metadata } from "next";
import "./globals.css";
import { AuthProvider } from "./components/AuthProvider";
import { ToastProvider } from "./components/Toast";
import { BrandingProvider } from "./components/BrandingContext";
import { ConversationProvider } from "./components/ConversationContext";

export const metadata: Metadata = {
  title: "SynaptDI",
  description: "SynaptDI — Enterprise domains at your fingertips",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="antialiased">
        <AuthProvider>
          <BrandingProvider>
            <ConversationProvider>
              <ToastProvider>
                {children}
              </ToastProvider>
            </ConversationProvider>
          </BrandingProvider>
        </AuthProvider>
      </body>
    </html>
  );
}
