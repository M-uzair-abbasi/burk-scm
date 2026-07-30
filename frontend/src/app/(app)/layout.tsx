"use client";

import { useEffect, type ReactNode } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";

import { useAuth } from "@/components/AuthProvider";

const NAV = [
  { href: "/dashboard", label: "Dashboard", managerOnly: false },
  { href: "/orders", label: "Orders", managerOnly: false },
  { href: "/inventory", label: "Inventory", managerOnly: false },
  { href: "/suppliers", label: "Suppliers", managerOnly: true },
  { href: "/purchase-orders", label: "Purchase Orders", managerOnly: true },
];

export default function AppLayout({ children }: { children: ReactNode }) {
  const { user, loading, logout } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  // Guard: bounce to /login once we know there is no session.
  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [loading, user, router]);

  if (loading || !user) {
    return (
      <div className="flex min-h-screen items-center justify-center text-sm text-zinc-500">
        Loading…
      </div>
    );
  }

  const nav = NAV.filter((item) => !item.managerOnly || user.is_manager);
  const current = nav.find(
    (item) => pathname === item.href || pathname.startsWith(item.href + "/"),
  );

  async function onLogout() {
    await logout();
    router.replace("/login");
  }

  return (
    <div className="flex min-h-screen">
      {/* Sidebar */}
      <aside className="flex w-60 shrink-0 flex-col border-r border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
        <div className="border-b border-zinc-200 px-5 py-4 dark:border-zinc-800">
          <div className="text-sm font-semibold tracking-tight">Burk.pk SCM-OVS</div>
          <div className="text-xs text-zinc-500">Warehouse Console</div>
        </div>
        <nav className="flex-1 space-y-1 p-3">
          {nav.map((item) => {
            const active =
              pathname === item.href || pathname.startsWith(item.href + "/");
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`block rounded-md px-3 py-2 text-sm font-medium transition-colors ${
                  active
                    ? "bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900"
                    : "text-zinc-600 hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-zinc-800"
                }`}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>
      </aside>

      {/* Main column */}
      <div className="flex flex-1 flex-col">
        <header className="flex items-center justify-between border-b border-zinc-200 bg-white px-6 py-3 dark:border-zinc-800 dark:bg-zinc-900">
          <h1 className="text-base font-semibold">{current?.label ?? ""}</h1>
          <div className="flex items-center gap-3">
            <div className="text-right">
              <div className="text-sm font-medium">{user.username}</div>
              <span
                className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${
                  user.is_manager
                    ? "bg-indigo-100 text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300"
                    : "bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300"
                }`}
              >
                {user.role}
              </span>
            </div>
            <button
              onClick={onLogout}
              className="rounded-md border border-zinc-300 px-3 py-1.5 text-sm font-medium text-zinc-700 transition-colors hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-800"
            >
              Log out
            </button>
          </div>
        </header>

        <main className="flex-1 overflow-y-auto p-6">{children}</main>
      </div>
    </div>
  );
}
