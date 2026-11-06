"use client";

import { useEffect, type ReactNode } from "react";
import { useRouter } from "next/navigation";

import { useAuth } from "@/components/AuthProvider";
import { AppShell } from "@/components/shell/AppShell";

/**
 * Auth boundary for every signed-in screen. The chrome itself lives in
 * AppShell — this file's only job is deciding whether the user may see it.
 */
export default function AppLayout({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [loading, user, router]);

  if (loading || !user) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="flex items-center gap-2.5 text-sm text-secondary">
          <span
            aria-hidden
            className="size-1.5 rounded-full bg-accent live-dot"
          />
          Loading your console…
        </div>
      </div>
    );
  }

  return <AppShell>{children}</AppShell>;
}
