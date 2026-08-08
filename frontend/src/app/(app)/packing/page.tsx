"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { ChannelBadge } from "@/components/ChannelBadge";
import { ApiError } from "@/lib/api";
import { packing } from "@/lib/resources";
import { formatDateTime, formatPKR } from "@/lib/format";
import type { PackQueueOrder } from "@/lib/types";

export default function PackingQueuePage() {
  const router = useRouter();
  const [rows, setRows] = useState<PackQueueOrder[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(() => {
    return packing
      .queue()
      .then(setRows)
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  async function startPacking(order: PackQueueOrder) {
    setError(null);
    setBusyId(order.id);
    try {
      const session = await packing.start(order.id);
      router.push(`/packing/${session.id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not start packing.");
      setBusyId(null);
    }
  }

  if (loading) return <p className="text-sm text-zinc-500">Loading…</p>;

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-zinc-200 bg-white px-4 py-3 text-sm text-zinc-600 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-300">
        Orders awaiting packing, oldest first. Open one and scan each item to
        verify it before sealing — the station blocks any item that doesn&apos;t
        belong to the order.
      </div>

      {error && (
        <div className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950 dark:text-red-300">
          {error}
        </div>
      )}

      {rows.length === 0 ? (
        <div className="rounded-xl border border-zinc-200 bg-white px-5 py-8 text-center text-sm text-zinc-500 dark:border-zinc-800 dark:bg-zinc-900">
          Nothing to pack. New orders appear here once they&apos;re synced into the
          queue.
        </div>
      ) : (
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
                <th className="px-4 py-3 font-medium">Placed</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-100 dark:divide-zinc-800">
              {rows.map((o) => (
                <tr key={o.id} className="hover:bg-zinc-50 dark:hover:bg-zinc-800/50">
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
                  <td className="px-4 py-3 text-right tabular-nums">{o.item_count}</td>
                  <td className="px-4 py-3 text-right tabular-nums">
                    {formatPKR(o.total)}
                  </td>
                  <td className="px-4 py-3 text-xs text-zinc-500">
                    {formatDateTime(o.placed_at)}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <button
                      disabled={busyId === o.id}
                      onClick={() => startPacking(o)}
                      className="rounded-md bg-zinc-900 px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-zinc-700 disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-300"
                    >
                      {busyId === o.id ? "…" : "Start packing"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
