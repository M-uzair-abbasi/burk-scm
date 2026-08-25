"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

import { StockStatusPill } from "@/components/StockStatusPill";
import { useAuth } from "@/components/AuthProvider";
import { dashboard, health, metrics, products } from "@/lib/resources";
import { formatNumber } from "@/lib/format";
import type {
  DashboardSummary,
  OperationalHealth,
  OperationalMetrics,
  Product,
} from "@/lib/types";

function formatDuration(seconds: number | null): string {
  if (seconds === null) return "No evidence";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
  return `${(seconds / 3600).toFixed(1)}h`;
}

function Card({
  label,
  value,
  tone = "default",
}: {
  label: string;
  value: number;
  tone?: "default" | "warn" | "danger";
}) {
  const toneCls =
    tone === "danger"
      ? "text-red-600 dark:text-red-400"
      : tone === "warn"
        ? "text-amber-600 dark:text-amber-400"
        : "text-zinc-900 dark:text-zinc-100";
  return (
    <div className="rounded-xl border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-900">
      <div className="text-sm text-zinc-500">{label}</div>
      <div className={`mt-1 text-3xl font-semibold ${toneCls}`}>
        {formatNumber(value)}
      </div>
    </div>
  );
}

export default function DashboardPage() {
  const { user } = useAuth();
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [lowStock, setLowStock] = useState<Product[]>([]);
  const [opsHealth, setOpsHealth] = useState<OperationalHealth | null>(null);
  const [opsMetrics, setOpsMetrics] = useState<OperationalMetrics | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadAllLowStock(): Promise<Product[]> {
      // /api/products/ is paginated (PAGE_SIZE=25); a real deployment can
      // have more low-stock SKUs than that, so page through everything
      // rather than silently showing only the first page.
      const all: Product[] = [];
      let page = 1;
      while (true) {
        const batch = await products.list({ low_stock: true, page });
        all.push(...batch.results);
        if (!batch.next) break;
        page += 1;
      }
      return all;
    }

    Promise.all([
      dashboard.summary(),
      loadAllLowStock(),
      user?.is_manager ? health.get() : Promise.resolve(null),
      user?.is_manager ? metrics.get() : Promise.resolve(null),
    ])
      .then(([s, low, operational, operationalMetrics]) => {
        setSummary(s);
        setLowStock(low);
        setOpsHealth(operational);
        setOpsMetrics(operationalMetrics);
      })
      .catch(() => setError("Could not load the dashboard."));
  }, [user?.is_manager]);

  if (error) {
    return <p className="text-sm text-red-600">{error}</p>;
  }
  if (!summary) {
    return <p className="text-sm text-zinc-500">Loading…</p>;
  }

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card label="Total SKUs" value={summary.total_skus} />
        <Card label="Low stock" value={summary.low_stock_count} tone="warn" />
        <Card
          label="Out of stock"
          value={summary.out_of_stock_count}
          tone="danger"
        />
        <Card label="Open purchase orders" value={summary.open_po_count} />
      </div>

      {user?.is_manager && opsHealth && (
        <div
          className={`rounded-xl border p-5 ${
            opsHealth.ok
              ? "border-emerald-200 bg-emerald-50 dark:border-emerald-900 dark:bg-emerald-950/40"
              : "border-red-200 bg-red-50 dark:border-red-900 dark:bg-red-950/40"
          }`}
        >
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <h2 className="text-sm font-semibold">Operational readiness</h2>
              <p className="mt-0.5 text-xs text-zinc-500">
                Database, worker, queue, media storage, and configured adapters
              </p>
            </div>
            <span
              className={`rounded-full px-2.5 py-1 text-xs font-semibold ${
                opsHealth.ok
                  ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-900 dark:text-emerald-200"
                  : "bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-200"
              }`}
            >
              {opsHealth.ok ? "Ready" : "Attention required"}
            </span>
          </div>
          <div className="mt-4 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
            <div>
              <div className="text-xs text-zinc-500">Worker heartbeat</div>
              <div className="font-medium">
                {opsHealth.components.worker.age_seconds === null
                  ? "Missing"
                  : `${opsHealth.components.worker.age_seconds.toFixed(0)}s ago`}
              </div>
            </div>
            <div>
              <div className="text-xs text-zinc-500">Due jobs</div>
              <div className="font-medium">{opsHealth.components.backlog.due}</div>
            </div>
            <div>
              <div className="text-xs text-zinc-500">Failed jobs</div>
              <div className="font-medium">{opsHealth.components.backlog.failed}</div>
            </div>
            <div>
              <div className="text-xs text-zinc-500">Adapters</div>
              <div className="font-medium">
                {opsHealth.components.adapters.details.filter((item) => item.ok).length}/
                {opsHealth.components.adapters.details.length} available
              </div>
            </div>
          </div>
        </div>
      )}

      {user?.is_manager && opsMetrics && (
        <section className="overflow-hidden rounded-xl border border-zinc-200 bg-zinc-950 text-zinc-100 dark:border-zinc-700">
          <div className="flex flex-wrap items-start justify-between gap-3 border-b border-zinc-800 px-5 py-4">
            <div>
              <div className="font-mono text-[11px] uppercase tracking-[0.16em] text-zinc-500">
                Warehouse control rail · {opsMetrics.window.hours}h
              </div>
              <h2 className="mt-1 text-base font-semibold">Operational signals</h2>
            </div>
            <span
              className={`rounded-full px-2.5 py-1 text-xs font-semibold ${
                opsMetrics.ok
                  ? "bg-emerald-400/15 text-emerald-300"
                  : "bg-red-400/15 text-red-300"
              }`}
            >
              {opsMetrics.ok
                ? "Within thresholds"
                : `${opsMetrics.breaches.length} threshold ${opsMetrics.breaches.length === 1 ? "breach" : "breaches"}`}
            </span>
          </div>

          <div className="grid grid-cols-2 divide-x divide-y divide-zinc-800 sm:grid-cols-3 lg:grid-cols-6">
            {[
              ["Jobs due", formatNumber(opsMetrics.queue.due), `${opsMetrics.queue.failed} failed`],
              ["Source lag", formatDuration(opsMetrics.sources.max_lag_seconds), `${opsMetrics.sources.missing.length} missing`],
              ["Wrong items blocked", formatNumber(opsMetrics.packing.mismatches_intercepted), `${opsMetrics.packing.scans} scans`],
              ["Delivery latency", formatDuration(opsMetrics.notifications.max_latency_seconds), `${opsMetrics.notifications.failed} failed`],
              ["Media processing", formatDuration(opsMetrics.media.max_processing_seconds), `${opsMetrics.media.failed} failed`],
              ["Booking failures", formatNumber(opsMetrics.shipments.booking_failures), "Courier jobs"],
            ].map(([label, value, detail]) => (
              <div key={label} className="min-w-0 px-4 py-4">
                <div className="truncate text-xs text-zinc-500">{label}</div>
                <div className="mt-1 font-mono text-xl font-semibold tracking-tight">
                  {value}
                </div>
                <div className="mt-0.5 truncate text-[11px] text-zinc-600">{detail}</div>
              </div>
            ))}
          </div>

          {!opsMetrics.ok && (
            <div className="border-t border-red-900/60 bg-red-950/30 px-5 py-3">
              <p className="text-xs font-semibold text-red-300">Needs attention</p>
              <ul className="mt-1 space-y-1 font-mono text-[11px] text-red-200/80">
                {opsMetrics.breaches.slice(0, 4).map((breach) => (
                  <li key={breach.code}>{breach.code.replaceAll(".", " / ")}</li>
                ))}
              </ul>
            </div>
          )}
        </section>
      )}

      <div className="rounded-xl border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
        <div className="flex items-center justify-between border-b border-zinc-200 px-5 py-3 dark:border-zinc-800">
          <h2 className="text-sm font-semibold">Low-stock items</h2>
          <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-800 dark:bg-amber-950 dark:text-amber-300">
            {lowStock.length}
          </span>
        </div>

        {lowStock.length === 0 ? (
          <p className="px-5 py-6 text-sm text-zinc-500">
            Nothing below its safety threshold. All good.
          </p>
        ) : (
          <ul className="divide-y divide-zinc-100 dark:divide-zinc-800">
            {lowStock.map((p) => (
              <li key={p.id}>
                <Link
                  href={`/inventory/${p.id}`}
                  className="flex items-center justify-between px-5 py-3 transition-colors hover:bg-zinc-50 dark:hover:bg-zinc-800/50"
                >
                  <div>
                    <div className="text-sm font-medium">{p.name}</div>
                    <div className="font-mono text-xs text-zinc-500">{p.sku}</div>
                  </div>
                  <div className="flex items-center gap-4">
                    <div className="text-right text-sm">
                      <span className="font-medium">{p.quantity_on_hand}</span>
                      <span className="text-zinc-400"> / {p.safety_stock}</span>
                    </div>
                    <StockStatusPill product={p} />
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
