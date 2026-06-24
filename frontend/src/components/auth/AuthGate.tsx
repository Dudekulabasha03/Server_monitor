"use client";
import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import { Sidebar } from "@/components/layout/Sidebar";
import { TopBar } from "@/components/layout/TopBar";
import { useAuthStore } from "@/lib/auth";

const PUBLIC_ROUTES = ["/login", "/register"];

// Environment banner — shown in DEV to prevent accidental prod changes
const ENV = process.env.NEXT_PUBLIC_ENV ?? "production";
const IS_DEV = ENV === "development";

function EnvBanner() {
  if (!IS_DEV) return null;
  return (
    <div className="bg-amber-500 text-black text-xs font-bold text-center py-0.5 px-2 flex items-center justify-center gap-2 flex-shrink-0">
      <span>⚠ DEV ENVIRONMENT</span>
      <span className="opacity-60">|</span>
      <span className="font-normal opacity-80">Changes here are safe to test — run promote.sh to push to PROD</span>
    </div>
  );
}

export function AuthGate({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { user, isLoading, loadFromStorage } = useAuthStore();

  const isPublicRoute = PUBLIC_ROUTES.includes(pathname);

  useEffect(() => {
    loadFromStorage();
  }, [loadFromStorage]);

  useEffect(() => {
    if (isLoading) return;
    if (!user && !isPublicRoute) {
      router.replace("/login");
    }
    if (user && isPublicRoute) {
      const dashboards: Record<string, string> = {
        super_admin: "/admin",
        admin: "/admin-ops",
        user: "/user-home",
      };
      router.replace(dashboards[user.role] ?? "/");
    }
  }, [user, isLoading, isPublicRoute, router]);

  if (isPublicRoute) return <>{children}</>;

  if (isLoading || !user) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-cyan-400" />
      </div>
    );
  }

  return (
    <div className="flex flex-col h-screen overflow-hidden">
      <EnvBanner />
      <div className="flex flex-1 overflow-hidden">
        <Sidebar />
        <div className="flex flex-col flex-1 overflow-hidden">
          <TopBar />
          <main className="flex-1 overflow-y-auto p-6">{children}</main>
        </div>
      </div>
    </div>
  );
}
