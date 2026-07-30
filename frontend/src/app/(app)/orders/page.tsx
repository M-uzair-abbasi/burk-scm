"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { ChannelBadge } from "@/components/ChannelBadge";
import { OrderStatusPill } from "@/components/OrderStatusPill";
import { ApiError } from "@/lib/api";
import { orders as ordersApi } from "@/lib/resources";
import { formatDateTime, formatPKR } from "@/lib/format";
import type { OrderSummary, SalesOrder } from "@/lib/types";

const STATUS_OPTIONS = [
  { value: "", label: "All statuses" },
  { value: "pending", label: "Pending" },
  { value: "confirmed", label: "Confirmed" },
  { value: "packed", label: "Packed" },
  { value: "shipped", label: "Shipped" },
  { value: "delivered", label: "Delivered" },
  { value: "cancelled", label: "Cancelled" },
  { value: "returned", label: "Returned" },
];

const CHANNEL_OPTIONS = [
  { value: "", label: "All channels" },
  { value: "burk", label: "Burk.pk" },
  { value: "daraz", label: "Daraz.pk" },
];

export default function OrdersPage() {
  const router = useRouter();
  const [rows, setRows] = useState<SalesOrder[]>([]);
  const [summary, setSummary] = useState<OrderSummary | null>(null);
  const [channel, setChannel] = useState("");
  const [status, setStatus] = useState("");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadList = useCallback(() => {
    return ordersApi
      .list({
        channel: channel || undefined,
        status: status || undefined,
        search,
      })
      .then((r) => setRows(r.results));
  }, [channel, status, search]);

  useEffect(() => {
    ordersApi.summary().then(setSummary).catch(() => {});
  }, []);

  // Debounce so typing in the search box doesn't fire a request per keystroke.
  useEffect(() => {
    setLoading(true);
    const t = setTimeout(() => {
      loadList().finally(() => setLoading(false));
    }, 250);
    return () => clearTimeout(t);
  }, [loadList]);

  async function onSync() {
    setError(null);
    setSyncing(true);
    try {
      const res = await ordersApi.sync();
      const created = res.runs.reduce((a, r) => a + r.created, 0);
      const updated = res.runs.reduce((a, r) => a + r.updated, 0);
      const dup = res.runs.reduce((a, r) => a + r.duplicates_skipped, 0);
      setToast(
        `Synced: ${created} new, ${updated} updated, ${dup} duplicate(s) skipped.`,
      );
      setSummary(res.summary);
      await loadList();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Sync failed.");
    } finally {
      setSyncing(false);
      setTimeout(() => setToast(null), 6000);
    }
  }

  const integrity = summary?.integrity;

  return (
    <div className="space-y-4">
      {/* Reconciliation strip — KPI #3 made visible */}
      <div className="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex flex-wrap items-center gap-3">
            {integrity && (
              <span
                className={`rounded-lg px-3 py-2 text-sm font-semibold ${
                  integrity.ok
                    ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300"
                    : "bg-red-50 text-red-700 dark:bg-red-950 dark:text-red-300"
                }`}
              >
                {integrity.dropped} dropped · {integrity.duplicated} duplicated ·{" "}
                {integrity.unique} unique
              </span>
            )}
            {summary &&
              Object.entries(summary.by_channel).map(([key, c]) => (
                <div
                  key={key}
                  className="rounded-lg border border-zinc-200 px-3 py-1.5 dark:border-zinc-800"
                >
                  <div className="text-sm font-semibold">
                    {c.label}: <span className="tabular-nums">{c.count}</span>
                  </div>
                  <div className="text-xs text-zinc-500">
                    last sync {formatDateTime(c.last_sync)}
                  </div>
                </div>
              ))}
          </div>
          <button
            onClick={onSync}
            disabled={syncing}
            className="rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-zinc-700 disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-300"
          >
            {syncing ? "Syncing…" : "Sync now"}
          </button>
        </div>
        {toast && (
          <div className="mt-3 rounded-md bg-emerald-50 px-3 py-2 text-sm text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300">
            {toast}
          </div>
        )}
        {error && (
          <div className="mt-3 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950 dark:text-red-300">
            {error}
          </div>
        )}
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3">
        <input
          type="search"
          placeholder="Search reference, order id or customer…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-72 rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm outline-none focus:border-zinc-900 dark:border-zinc-700 dark:bg-zinc-900"
        />
        <select
          value={channel}
          onChange={(e) => setChannel(e.target.value)}
          className="rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm outline-none focus:border-zinc-900 dark:border-zinc-700 dark:bg-zinc-900"
        >
          {CHANNEL_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
        <select
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          className="rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm outline-none focus:border-zinc-900 dark:border-zinc-700 dark:bg-zinc-900"
        >
          {STATUS_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      </div>

      {/* Queue */}
      <div className="overflow-x-auto rounded-xl border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-zinc-200 text-left text-xs uppercase tracking-wide text-zinc-500 dark:border-zinc-800">
              <th className="px-4 py-3 font-medium">Ref</th>
              <th className="px-4 py-3 font-medium">Channel</th>
              <th className="px-4 py-3 font-medium">Order #</th>
              <th className="px-4 py-3 font-medium">Customer</th>
              <th className="px-4 py-3 text-right font-medium">Items</th>
              <th className="px-4 py-3 text-right font-medium">Total</th>
              <th className="px-4 py-3 font-medium">Status</th>
              <th className="px-4 py-3 font-medium">Placed</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-100 dark:divide-zinc-800">
            {loading ? (
              <tr>
                <td colSpan={8} className="px-4 py-8 text-center text-zinc-500">
                  Loading…
                </td>
              </tr>
            ) : rows.length === 0 ? (
              <tr>
                <td colSpan={8} className="px-4 py-8 text-center text-zinc-500">
                  No orders match. Click “Sync now” to pull from the channels.
                </td>
              </tr>
            ) : (
              rows.map((o) => (
                <tr
                  key={o.id}
                  onClick={() => router.push(`/orders/${o.id}`)}
                  className="cursor-pointer transition-colors hover:bg-zinc-50 dark:hover:bg-zinc-800/50"
                >
                  <td className="px-4 py-3 font-mono text-xs font-semibold">
                    {o.reference}
                  </td>
                  <td className="px-4 py-3">
                    <ChannelBadge channel={o.channel} label={o.channel_display} />
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-zinc-500">
                    {o.external_id}
                  </td>
                  <td className="px-4 py-3 font-medium">{o.customer_name || "—"}</td>
                  <td className="px-4 py-3 text-right tabular-nums">
                    {o.item_count}
                  </td>
                  <td className="px-4 py-3 text-right font-medium tabular-nums">
                    {formatPKR(o.total)}
                  </td>
                  <td className="px-4 py-3">
                    <OrderStatusPill status={o.status} label={o.status_display} />
                  </td>
                  <td className="px-4 py-3 text-xs text-zinc-500">
                    {formatDateTime(o.placed_at)}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
