"use client";
import { useAuthStore, UserRole, isAtLeast } from "@/lib/auth";
import { ShieldOff } from "lucide-react";

interface RoleGuardProps {
  roles?: UserRole[];
  minRole?: UserRole;
  children: React.ReactNode;
  fallback?: React.ReactNode;
}

export function RoleGuard({ roles, minRole, children, fallback }: RoleGuardProps) {
  const user = useAuthStore((s) => s.user);

  if (!user) return null;

  const allowed =
    (roles && roles.includes(user.role)) ||
    (minRole && isAtLeast(user.role, minRole)) ||
    (!roles && !minRole);

  if (!allowed) {
    return (
      fallback ?? (
        <div className="flex flex-col items-center justify-center h-64 text-text-muted gap-3">
          <ShieldOff size={40} className="text-red-400/50" />
          <p className="font-medium">Access Denied</p>
          <p className="text-sm">You don&apos;t have permission to view this content.</p>
        </div>
      )
    );
  }

  return <>{children}</>;
}
