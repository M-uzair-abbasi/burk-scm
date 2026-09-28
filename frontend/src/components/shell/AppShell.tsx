"use client";

import { useState, type ReactNode } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import * as RD from "@radix-ui/react-dialog";
import * as RP from "@radix-ui/react-popover";
import {
  Boxes,
  Building2,
  ClipboardList,
  Compass,
  LayoutDashboard,
  LogOut,
  Menu,
  ScanLine,
  ShoppingCart,
  X,
  type LucideIcon,
} from "lucide-react";

import { useAuth } from "@/components/AuthProvider";
import { cn } from "@/components/ui/cn";
import { FirstRunTour, START_TOUR_EVENT } from "./FirstRunTour";
import { useOpsCounts, type OpsCounts } from "./useOpsCounts";

interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  managerOnly?: boolean;
  /** Which live count to badge this item with, if any. */
  count?: keyof Pick<OpsCounts, "packQueue" | "lowStock" | "openPOs">;
}

/**
 * The nav is split by *what you do with it*, not alphabetically.
 *
 * TODAY holds the work queues — things that are waiting for a person right
 * now, each badged with how many. REFERENCE holds the records you look things
 * up in. The old flat list of six nouns gave a newcomer no way to tell which
 * screen their job actually lives on.
 */
const SECTIONS: { label: string; items: NavItem[] }[] = [
  {
    label: "Today",
    items: [
      { href: "/dashboard", label: "Overview", icon: LayoutDashboard },
      {
        href: "/packing",
        label: "Packing station",
        icon: ScanLine,
        count: "packQueue",
      },
      { href: "/orders", label: "Orders", icon: ShoppingCart },
    ],
  },
  {
    label: "Reference",
    items: [
      { href: "/inventory", label: "Inventory", icon: Boxes, count: "lowStock" },
      {
        href: "/suppliers",
        label: "Suppliers",
        icon: Building2,
        managerOnly: true,
      },
      {
        href: "/purchase-orders",
        label: "Purchase orders",
        icon: ClipboardList,
        managerOnly: true,
      },
    ],
  },
];

function isActive(pathname: string, href: string): boolean {
  return pathname === href || pathname.startsWith(href + "/");
}

function NavLinks({
  counts,
  isManager,
  onNavigate,
}: {
  counts: OpsCounts;
  isManager: boolean;
  onNavigate?: () => void;
}) {
  const pathname = usePathname();

  return (
    <nav className="flex flex-col gap-6 p-3">
      {SECTIONS.map((section) => {
        const items = section.items.filter(
          (item) => !item.managerOnly || isManager,
        );
        if (items.length === 0) return null;

        return (
          <div key={section.label}>
            <div className="eyebrow px-3 pb-2 text-muted">{section.label}</div>
            <div className="flex flex-col gap-0.5">
              {items.map((item) => {
                const active = isActive(pathname, item.href);
                const badge = item.count ? counts[item.count] : 0;
                const Icon = item.icon;

                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    onClick={onNavigate}
                    aria-current={active ? "page" : undefined}
                    className={cn(
                      "group flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm transition-colors duration-150",
                      active
                        ? "bg-accent-soft font-medium text-accent-text"
                        : "text-secondary hover:bg-hover hover:text-primary",
                    )}
                  >
                    <Icon
                      aria-hidden
                      className={cn(
                        "size-4 shrink-0",
                        active ? "text-accent" : "text-muted",
                      )}
                    />
                    <span className="flex-1 truncate">{item.label}</span>
                    {badge > 0 ? (
                      <span
                        className={cn(
                          "tabular rounded-full px-1.5 py-0.5 text-[11px] font-semibold",
                          "bg-warning-soft text-warning-text",
                        )}
                      >
                        {badge}
                      </span>
                    ) : null}
                  </Link>
                );
              })}
            </div>
          </div>
        );
      })}
    </nav>
  );
}

function StatusLamp({ ok }: { ok: boolean | null }) {
  const label =
    ok === null ? "Checking…" : ok ? "All systems live" : "Attention needed";
  const dot =
    ok === null ? "bg-neutral-signal" : ok ? "bg-success" : "bg-warning";

  return (
    <span
      className="inline-flex items-center gap-2 rounded-full border border-subtle bg-raised px-2.5 py-1"
      title={label}
    >
      <span
        aria-hidden
        className={cn("size-1.5 rounded-full", dot, ok === true && "live-dot")}
      />
      <span className="eyebrow text-secondary">
        {ok === null ? "…" : ok ? "Live" : "Check"}
      </span>
    </span>
  );
}

function UserMenu() {
  const { user, logout } = useAuth();
  const router = useRouter();
  const [open, setOpen] = useState(false);

  if (!user) return null;

  const initial = (user.username[0] ?? "?").toUpperCase();
  const fullName = [user.first_name, user.last_name]
    .filter(Boolean)
    .join(" ")
    .trim();

  async function onLogout() {
    await logout();
    router.replace("/login");
  }

  return (
    <RP.Root open={open} onOpenChange={setOpen}>
      <RP.Trigger
        className="flex items-center gap-2 rounded-lg px-1.5 py-1 transition-colors duration-150 hover:bg-hover"
        aria-label="Account menu"
      >
        <span className="flex size-7 items-center justify-center rounded-full bg-accent text-xs font-semibold text-accent-on">
          {initial}
        </span>
        <span className="hidden text-sm font-medium text-primary sm:inline">
          {user.username}
        </span>
      </RP.Trigger>

      <RP.Portal>
        <RP.Content
          align="end"
          sideOffset={8}
          className="z-50 w-56 overflow-hidden rounded-xl border border-subtle bg-raised shadow-overlay"
        >
          {/* The old header printed username and role side by side, which read
              as a duplicate for the "manager" account. Role is secondary
              information, so it belongs here, described rather than repeated. */}
          <div className="border-b border-subtle px-4 py-3">
            <div className="truncate text-sm font-medium text-primary">
              {fullName || user.username}
            </div>
            <div className="mt-0.5 text-xs text-secondary">
              {user.is_manager
                ? "Manager — full access"
                : "Operator — packing and stock"}
            </div>
          </div>
          <button
            onClick={() => {
              setOpen(false);
              window.dispatchEvent(new Event(START_TOUR_EVENT));
            }}
            className="flex w-full items-center gap-2 px-4 py-2.5 text-left text-sm text-secondary transition-colors duration-150 hover:bg-hover hover:text-primary"
          >
            <Compass aria-hidden className="size-4" />
            Replay the tour
          </button>
          <button
            onClick={onLogout}
            className="flex w-full items-center gap-2 border-t border-subtle px-4 py-2.5 text-left text-sm text-secondary transition-colors duration-150 hover:bg-hover hover:text-primary"
          >
            <LogOut aria-hidden className="size-4" />
            Log out
          </button>
        </RP.Content>
      </RP.Portal>
    </RP.Root>
  );
}

function Wordmark() {
  return (
    <Link href="/dashboard" className="flex items-center gap-2.5">
      <span
        aria-hidden
        className="flex size-7 items-center justify-center rounded-md bg-instrument text-[11px] font-bold tracking-tight text-instrument-text"
      >
        BK
      </span>
      <span className="leading-tight">
        <span className="block text-sm font-semibold tracking-tight text-primary">
          Burk.pk SCM-OVS
        </span>
        <span className="eyebrow block text-muted">Warehouse console</span>
      </span>
    </Link>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const counts = useOpsCounts();
  const [drawerOpen, setDrawerOpen] = useState(false);

  const isManager = user?.is_manager ?? false;

  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-30 flex h-14 shrink-0 items-center justify-between gap-3 border-b border-subtle bg-raised px-4 lg:px-6">
        <div className="flex items-center gap-3">
          <RD.Root open={drawerOpen} onOpenChange={setDrawerOpen}>
            <RD.Trigger
              className="-ml-1 rounded-md p-2 text-secondary transition-colors duration-150 hover:bg-hover lg:hidden"
              aria-label="Open navigation"
            >
              <Menu className="size-5" />
            </RD.Trigger>
            <RD.Portal>
              <RD.Overlay className="fixed inset-0 z-40 bg-instrument/55 lg:hidden" />
              <RD.Content className="fixed inset-y-0 left-0 z-50 w-72 overflow-y-auto border-r border-subtle bg-raised focus:outline-none lg:hidden">
                <RD.Title className="sr-only">Navigation</RD.Title>
                <div className="flex items-center justify-between border-b border-subtle px-4 py-3.5">
                  <Wordmark />
                  <RD.Close
                    aria-label="Close navigation"
                    className="rounded-md p-1.5 text-muted transition-colors duration-150 hover:bg-hover hover:text-primary"
                  >
                    <X className="size-4" />
                  </RD.Close>
                </div>
                {/* Closing on navigate (rather than watching the pathname in
                    an effect) keeps the drawer from covering the page it just
                    opened, without a state update during render. */}
                <NavLinks
                  counts={counts}
                  isManager={isManager}
                  onNavigate={() => setDrawerOpen(false)}
                />
              </RD.Content>
            </RD.Portal>
          </RD.Root>

          <Wordmark />
        </div>

        <div className="flex items-center gap-3">
          {counts.healthAvailable ? <StatusLamp ok={counts.healthOk} /> : null}
          <UserMenu />
        </div>
      </header>

      <div className="flex flex-1">
        <aside className="hidden w-60 shrink-0 border-r border-subtle bg-raised lg:block">
          <div className="sticky top-14">
            <NavLinks counts={counts} isManager={isManager} />
          </div>
        </aside>

        <main className="min-w-0 flex-1 px-4 py-6 lg:px-8 lg:py-8">
          <div className="mx-auto max-w-[1400px]">{children}</div>
        </main>
      </div>

      <FirstRunTour isManager={isManager} />
    </div>
  );
}
