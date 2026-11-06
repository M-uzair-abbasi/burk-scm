"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Activity,
  ArrowRight,
  Boxes,
  CheckCircle2,
  ClipboardList,
  PackageX,
  ScanLine,
  ShoppingCart,
  Truck,
  TriangleAlert,
} from "lucide-react";

import { useAuth } from "@/components/AuthProvider";
import { Button, ButtonLink } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { InstrumentPanel, Panel } from "@/components/ui/Panel";
import { Meter } from "@/components/ui/Meter";
import { PageHeader } from "@/components/ui/PageHeader";
import { StatCard } from "@/components/ui/StatCard";
import { StatusPill } from "@/components/ui/StatusPill";
import { Term } from "@/components/ui/Tooltip";
import { cn } from "@/components/ui/cn";
import { stockLabel, stockTone } from "@/components/ui/status";
import {
  dashboard,
  health,
  metrics,
  orders as ordersApi,
  packing,
  products,
} from "@/lib/resources";
import { formatNumber } from "@/lib/format";
import { ApiError } from "@/lib/api";
import type {
  DashboardSummary,
  OperationalHealth,
  OperationalMetrics,
  OrderSummary,
  PackQueueOrder,
  Product,
} from "@/lib/types";

function formatDuration(seconds: number | null): string {
  if (seconds === null) return "No evidence";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
  return `${(seconds / 3600).toFixed(1)}h`;
}

/* ---------------------------------------------------------------------------
   NEXT UP — the answer to "I just opened this, what do I do?"
   A console that opens on a wall of metrics makes a newcomer guess. This card
   names one action, and only one, ranked by what the warehouse actually needs.
   ------------------------------------------------------------------------- */

function NextUp({
  queue,
  lowStockCount,
  loading,
}: {
  queue: PackQueueOrder[];
  lowStockCount: number;
  loading: boolean;
}) {
  const router = useRouter();
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);

  // /packing/[id] is keyed by pack *session*, not by order, so the session has
  // to be opened before we can navigate — the same two-step the queue page does.
  async function startPacking(orderId: number) {
    setStartError(null);
    setStarting(true);
    try {
      const session = await packing.start(orderId);
      router.push(`/packing/${session.id}`);
    } catch (err) {
      setStartError(
        err instanceof ApiError ? err.message : "Could not open the station.",
      );
      setStarting(false);
    }
  }

  if (loading) {
    return (
      <div className="h-[132px] animate-pulse rounded-xl border border-subtle bg-raised" />
    );
  }

  // Priority 1: orders physically waiting to be packed.
  if (queue.length > 0) {
    const next = queue[0];
    return (
      <section className="overflow-hidden rounded-xl border border-accent/40 bg-raised shadow-card">
        <div className="flex items-center gap-2 border-b border-accent/20 bg-accent-soft px-5 py-2">
          <ScanLine aria-hidden className="size-3.5 text-accent-text" />
          <span className="eyebrow text-accent-text">Next up</span>
        </div>
        <div className="flex flex-wrap items-center justify-between gap-4 px-5 py-4">
          <div className="min-w-0">
            <div className="flex flex-wrap items-baseline gap-x-2.5 gap-y-1">
              <span className="tabular font-mono text-[15px] font-semibold text-primary">
                {next.reference}
              </span>
              <span className="text-sm text-secondary">
                {next.customer_name}
              </span>
            </div>
            <p className="mt-1 text-sm text-secondary">
              {next.item_count} {next.item_count === 1 ? "item" : "items"} ·{" "}
              {next.channel_display}
              {queue.length > 1 ? (
                <>
                  {" "}
                  ·{" "}
                  <span className="text-muted">
                    {queue.length - 1} more waiting behind it
                  </span>
                </>
              ) : null}
            </p>
          </div>
          <Button
            onClick={() => startPacking(next.id)}
            disabled={starting}
            variant="primary"
            size="lg"
            className="w-full sm:w-auto"
          >
            {starting ? "Opening station…" : "Start packing"}
            <ArrowRight aria-hidden className="size-4" />
          </Button>
        </div>
        {startError ? (
          <p className="border-t border-critical/20 bg-critical-soft px-5 py-2.5 text-sm text-critical-text">
            {startError}
          </p>
        ) : null}
      </section>
    );
  }

  // Priority 2: nothing to pack, but stock needs replenishing.
  if (lowStockCount > 0) {
    return (
      <section className="overflow-hidden rounded-xl border border-warning/40 bg-raised shadow-card">
        <div className="flex items-center gap-2 border-b border-warning/20 bg-warning-soft px-5 py-2">
          <TriangleAlert aria-hidden className="size-3.5 text-warning-text" />
          <span className="eyebrow text-warning-text">Next up</span>
        </div>
        <div className="flex flex-wrap items-center justify-between gap-4 px-5 py-4">
          <div className="min-w-0">
            <p className="text-[15px] font-semibold text-primary">
              Packing queue is clear
            </p>
            <p className="mt-1 text-sm text-secondary">
              {lowStockCount}{" "}
              {lowStockCount === 1 ? "product is" : "products are"} at or below{" "}
              <Term definition="The stock level you never want to fall under. Drop to it and the item is flagged for reorder.">
                safety stock
              </Term>
              . Raising a purchase order is the useful thing to do next.
            </p>
          </div>
          <ButtonLink
            href="/inventory?low=1"
            variant="primary"
            size="lg"
            className="w-full sm:w-auto"
          >
            Review low stock
            <ArrowRight aria-hidden className="size-4" />
          </ButtonLink>
        </div>
      </section>
    );
  }

  // Priority 3: genuinely nothing pending.
  return (
    <section className="overflow-hidden rounded-xl border border-success/40 bg-raised shadow-card">
      <div className="flex items-center gap-2 border-b border-success/20 bg-success-soft px-5 py-2">
        <CheckCircle2 aria-hidden className="size-3.5 text-success-text" />
        <span className="eyebrow text-success-text">All clear</span>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-4 px-5 py-4">
        <div className="min-w-0">
          <p className="text-[15px] font-semibold text-primary">
            Nothing is waiting on you
          </p>
          <p className="mt-1 text-sm text-secondary">
            No orders to pack and no stock below its safety level. New orders
            arrive automatically from Burk.pk and Daraz.pk.
          </p>
        </div>
        <ButtonLink href="/orders" variant="secondary" size="lg">
          View all orders
          <ArrowRight aria-hidden className="size-4" />
        </ButtonLink>
      </div>
    </section>
  );
}

/* ---------------------------------------------------------------------------
   PIPELINE — makes the core loop legible in one glance.
   ------------------------------------------------------------------------- */

function Pipeline({
  byStatus,
  queueLength,
}: {
  byStatus: Record<string, number>;
  queueLength: number;
}) {
  const count = (...keys: string[]) =>
    keys.reduce((sum, key) => sum + (byStatus[key] ?? 0), 0);

  const stages = [
    {
      label: "Arrive",
      icon: ShoppingCart,
      value: count("pending", "confirmed"),
      blurb: "Pulled in automatically from Burk.pk and Daraz.pk",
      href: "/orders",
    },
    {
      label: "Verify & pack",
      icon: ScanLine,
      value: queueLength,
      blurb: "Every item barcode-scanned; wrong items are blocked",
      href: "/packing",
    },
    {
      label: "Seal & ship",
      icon: Truck,
      value: count("packed", "shipped"),
      blurb: "Packing video recorded, customer notified, courier booked",
      href: "/orders",
    },
    {
      label: "Delivered",
      icon: CheckCircle2,
      value: count("delivered"),
      blurb: "Courier confirms delivery and a review request goes out",
      href: "/orders",
    },
  ];

  return (
    <Panel
      eyebrow="How this warehouse runs"
      title="Order pipeline"
      icon={Activity}
      bodyClassName="grid grid-cols-1 divide-y divide-subtle sm:grid-cols-2 lg:grid-cols-4 lg:divide-y-0 lg:divide-x"
    >
      {stages.map((stage, index) => {
        const Icon = stage.icon;
        return (
          <a
            key={stage.label}
            href={stage.href}
            className="group flex flex-col gap-2 p-5 transition-colors duration-150 hover:bg-hover"
          >
            <div className="flex items-center gap-2">
              <span className="flex size-6 items-center justify-center rounded-md bg-sunken text-muted">
                <Icon aria-hidden className="size-3.5" />
              </span>
              <span className="eyebrow text-muted">
                {index + 1} · {stage.label}
              </span>
            </div>
            <div className="tabular text-2xl font-semibold leading-none text-primary">
              {formatNumber(stage.value)}
            </div>
            <p className="text-xs leading-relaxed text-secondary">
              {stage.blurb}
            </p>
          </a>
        );
      })}
    </Panel>
  );
}

/* ---------------------------------------------------------------------------
   SIGNALS — the dark instrument surface. Manager-only.
   ------------------------------------------------------------------------- */

function Signals({ m }: { m: OperationalMetrics }) {
  const readings = [
    {
      label: "Jobs due",
      value: formatNumber(m.queue.due),
      sub: `${m.queue.failed} failed`,
      bad: m.queue.failed > 0,
    },
    {
      label: "Source lag",
      value: formatDuration(m.sources.max_lag_seconds),
      sub: `${m.sources.missing.length} missing`,
      bad: m.sources.missing.length > 0,
    },
    {
      label: "Wrong items blocked",
      value: formatNumber(
        m.packing.mismatches_intercepted + m.packing.overscans_intercepted,
      ),
      sub: `${formatNumber(m.packing.scans)} scans`,
      bad: false,
    },
    {
      label: "Dispatch latency",
      value: formatDuration(m.notifications.average_latency_seconds),
      sub: `${m.notifications.failed} failed`,
      bad: m.notifications.failed > 0,
    },
    {
      label: "Media processing",
      value: formatDuration(m.media.average_processing_seconds),
      sub: `${m.media.failed} failed`,
      bad: m.media.failed > 0,
    },
    {
      label: "Booking failures",
      value: formatNumber(m.shipments.booking_failures),
      sub: "Courier jobs",
      bad: m.shipments.booking_failures > 0,
    },
  ];

  const breached = m.breaches.length > 0;

  return (
    <InstrumentPanel
      eyebrow={`Live signals · last ${m.window.hours}h`}
      title="Is the automation keeping up?"
      status={
        <span
          className={cn(
            "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium",
            breached
              ? "bg-warning/15 text-warning"
              : "bg-success/15 text-success",
          )}
        >
          <span
            aria-hidden
            className={cn(
              "size-1.5 rounded-full",
              breached ? "bg-warning" : "bg-success live-dot",
            )}
          />
          {breached
            ? `${m.breaches.length} threshold breach${m.breaches.length > 1 ? "es" : ""}`
            : "Within thresholds"}
        </span>
      }
    >
      <div className="grid grid-cols-2 divide-x divide-y divide-instrument-border md:grid-cols-3 lg:grid-cols-6 lg:divide-y-0">
        {readings.map((r) => (
          <div key={r.label} className="p-4">
            <div className="eyebrow text-instrument-muted">{r.label}</div>
            <div
              className={cn(
                "tabular mt-2 font-mono text-lg font-semibold leading-none",
                r.bad ? "text-warning" : "text-instrument-text",
              )}
            >
              {r.value}
            </div>
            <div className="mt-1.5 text-[11px] text-instrument-muted">
              {r.sub}
            </div>
          </div>
        ))}
      </div>

      {breached ? (
        <div className="border-t border-instrument-border bg-warning/10 px-5 py-3">
          <div className="eyebrow text-warning">Needs attention</div>
          <p className="mt-1.5 font-mono text-xs text-instrument-text">
            {m.breaches.map((b) => b.code).join(" · ")}
          </p>
          <p className="mt-1.5 text-[11px] leading-relaxed text-instrument-muted">
            A breach usually means a feed has not been pulled recently. Opening
            Orders and pressing &ldquo;Sync now&rdquo; clears a stale source lag.
          </p>
        </div>
      ) : null}
    </InstrumentPanel>
  );
}

/* ------------------------------------------------------------------------- */

export default function DashboardPage() {
  const { user } = useAuth();
  const isManager = user?.is_manager ?? false;

  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [lowStock, setLowStock] = useState<Product[]>([]);
  const [queue, setQueue] = useState<PackQueueOrder[]>([]);
  const [orderSummary, setOrderSummary] = useState<OrderSummary | null>(null);
  const [healthData, setHealthData] = useState<OperationalHealth | null>(null);
  const [metricsData, setMetricsData] = useState<OperationalMetrics | null>(
    null,
  );
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;

    // Each call is settled independently so that one refusal — health and
    // metrics are manager-only — cannot blank the panels an operator may see.
    async function load() {
      const [
        summaryRes,
        lowStockRes,
        queueRes,
        orderSummaryRes,
        healthRes,
        metricsRes,
      ] = await Promise.allSettled([
        dashboard.summary(),
        products.list({ low_stock: true }),
        packing.queue(),
        ordersApi.summary(),
        isManager ? health.get() : Promise.resolve(null),
        isManager ? metrics.get() : Promise.resolve(null),
      ]);
      if (!alive) return;

      if (summaryRes.status === "fulfilled") setSummary(summaryRes.value);
      if (lowStockRes.status === "fulfilled")
        setLowStock(lowStockRes.value.results);
      if (queueRes.status === "fulfilled") setQueue(queueRes.value);
      if (orderSummaryRes.status === "fulfilled")
        setOrderSummary(orderSummaryRes.value);
      if (healthRes.status === "fulfilled") setHealthData(healthRes.value);
      if (metricsRes.status === "fulfilled") setMetricsData(metricsRes.value);
      setLoading(false);
    }

    load();
    return () => {
      alive = false;
    };
  }, [isManager]);

  const greetingName = user?.first_name?.trim() || user?.username || "there";

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        title={`Welcome back, ${greetingName}`}
        description="This console runs one loop: orders arrive from your sales channels, every item is barcode-verified as it is packed, then the parcel is filmed, the customer notified and a courier booked — automatically."
      />

      <NextUp
        queue={queue}
        lowStockCount={summary?.low_stock_count ?? 0}
        loading={loading}
      />

      <Pipeline
        byStatus={orderSummary?.by_status ?? {}}
        queueLength={queue.length}
      />

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard
          label="Total SKUs"
          value={summary ? formatNumber(summary.total_skus) : "—"}
          icon={Boxes}
          href="/inventory"
          caption="Active products tracked"
        />
        <StatCard
          label="Low stock"
          value={summary ? formatNumber(summary.low_stock_count) : "—"}
          icon={TriangleAlert}
          tone={summary && summary.low_stock_count > 0 ? "warning" : "neutral"}
          href="/inventory?low=1"
          caption="At or below safety stock"
        />
        <StatCard
          label="Out of stock"
          value={summary ? formatNumber(summary.out_of_stock_count) : "—"}
          icon={PackageX}
          tone={
            summary && summary.out_of_stock_count > 0 ? "critical" : "neutral"
          }
          href="/inventory?low=1"
          caption="Cannot be fulfilled"
        />
        <StatCard
          label="Open purchase orders"
          value={summary ? formatNumber(summary.open_po_count) : "—"}
          icon={ClipboardList}
          href="/purchase-orders"
          caption="Awaiting delivery"
        />
      </div>

      {isManager && metricsData ? <Signals m={metricsData} /> : null}

      {isManager && healthData ? (
        <Panel
          eyebrow="Operational readiness"
          title="Database, worker, queue, media storage and adapters"
          icon={Activity}
          actions={
            <StatusPill
              tone={healthData.ok ? "success" : "warning"}
              variant={healthData.ok ? "solid" : "soft"}
            >
              {healthData.ok ? "Ready" : "Degraded"}
            </StatusPill>
          }
          bodyClassName="grid grid-cols-2 gap-px bg-subtle sm:grid-cols-4"
        >
          {[
            {
              label: "Worker heartbeat",
              value:
                healthData.components.worker.age_seconds === null
                  ? "—"
                  : `${Math.round(healthData.components.worker.age_seconds)}s ago`,
              ok: healthData.components.worker.ok,
            },
            {
              label: "Due jobs",
              value: formatNumber(healthData.components.backlog.due),
              ok: healthData.components.backlog.ok,
            },
            {
              label: "Failed jobs",
              value: formatNumber(healthData.components.backlog.failed),
              ok: healthData.components.backlog.failed === 0,
            },
            {
              label: "Adapters",
              value: `${healthData.components.adapters.details.filter((a) => a.ok).length}/${healthData.components.adapters.details.length} available`,
              ok: healthData.components.adapters.ok,
            },
          ].map((item) => (
            <div key={item.label} className="bg-raised p-4">
              <div className="eyebrow text-muted">{item.label}</div>
              <div
                className={cn(
                  "tabular mt-2 text-sm font-semibold",
                  item.ok ? "text-primary" : "text-warning",
                )}
              >
                {item.value}
              </div>
            </div>
          ))}
        </Panel>
      ) : null}

      <Panel
        eyebrow="Replenishment"
        title="Items at or below safety stock"
        icon={TriangleAlert}
        actions={
          lowStock.length > 0 ? (
            <ButtonLink href="/inventory?low=1" variant="secondary" size="sm">
              Open inventory
            </ButtonLink>
          ) : null
        }
        bodyClassName={lowStock.length === 0 ? "p-5" : undefined}
      >
        {lowStock.length === 0 ? (
          <EmptyState
            icon={CheckCircle2}
            title="Every product is above its safety level"
            body="Nothing needs reordering right now. Items appear here as soon as stock falls to its safety threshold."
            action={
              <ButtonLink href="/inventory" variant="secondary" size="sm">
                Browse inventory
              </ButtonLink>
            }
          />
        ) : (
          <ul className="divide-y divide-subtle">
            {lowStock.slice(0, 6).map((product) => {
              const tone = stockTone(
                product.quantity_on_hand,
                product.safety_stock,
              );
              return (
                <li
                  key={product.id}
                  className="flex items-center gap-4 px-5 py-3"
                >
                  <div className="min-w-0 flex-1">
                    <a
                      href={`/inventory/${product.id}`}
                      className="block truncate text-sm font-medium text-primary hover:text-accent-text"
                    >
                      {product.name}
                    </a>
                    <div className="tabular mt-0.5 font-mono text-xs text-muted">
                      {product.sku}
                    </div>
                  </div>
                  <div className="w-28 shrink-0">
                    <Meter
                      value={product.quantity_on_hand}
                      max={Math.max(product.safety_stock, 1)}
                      tone={tone}
                      label={`${product.name} stock level`}
                    />
                    <div className="tabular mt-1.5 text-right font-mono text-xs text-secondary">
                      {product.quantity_on_hand}
                      <span className="text-muted">
                        {" "}
                        / {product.safety_stock}
                      </span>
                    </div>
                  </div>
                  <StatusPill
                    tone={tone}
                    variant={tone === "critical" ? "solid" : "soft"}
                  >
                    {stockLabel(product.quantity_on_hand, product.safety_stock)}
                  </StatusPill>
                </li>
              );
            })}
          </ul>
        )}
      </Panel>
    </div>
  );
}
