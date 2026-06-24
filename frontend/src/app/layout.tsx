import type { Metadata } from "next";
import "./globals.css";
import { Providers } from "@/components/Providers";
import { AuthGate } from "@/components/auth/AuthGate";

export const metadata: Metadata = {
  title: "Helios — AMD Health Observability",
  description: "Helios — Datacenter Infrastructure Intelligence & Predictive Maintenance",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className="font-sans bg-background text-text-primary min-h-screen">
        <Providers>
          <AuthGate>{children}</AuthGate>
        </Providers>
      </body>
    </html>
  );
}
