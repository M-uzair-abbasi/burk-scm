"use client";

import { useCallback, useEffect, useState } from "react";

import { useAuth } from "@/components/AuthProvider";
import { ApiError } from "@/lib/api";
import { purchaseOrders } from "@/lib/resources";
import { formatDate, formatPKR } from "@/lib/format";
import type { POStatus, PurchaseOrder } from "@/lib/types";

const STATUS_STYLES: Record<POStatus, string> = {
  draft: "bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300",
  submitted: "bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-300",
  partially_received:
    "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300",
  received: "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300",
  cancelled: "bg-zinc-100 text-zinc-500 line-through dark:bg-zinc-800",
};

export default function PurchaseOrdersPage() {
  const { user } = useAuth();
  const [pos, setPos] = useState<PurchaseOrder[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(() => {
    return purchaseOrders
      .list()
      .then((r) => setPos(r.results))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  async function act(id: number, fn: () => Promise<unknown>) {
    setError(null);
    setBusyId(id);
    try {
      await fn();
      await reload();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Action failed.");
    } finally {
      setBusyId(null);
    }
  }

  if (loading) return <p className="text-sm text-zinc-500">Loading…</p>;

  return (
    <div className="space-y-4">
      {error && (
        <div className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950 dark:text-red-300">
          {error}
        </div>
      )}

      {pos.length === 0 ? (
        <div className="rounded-xl border border-zinc-200 bg-white px-5 py-8 text-center text-sm text-zinc-500 dark:border-zinc-800 dark:bg-zinc-900">
          No purchase orders yet. Reorder a low-stock product to create one.
        </div>
      ) : (
        pos.map((po) => (
          <div
            key={po.id}
            className="rounded-xl border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900"
          >
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-zinc-200 px-5 py-3 dark:border-zinc-800">
              <div className="flex items-center gap-3">
                <span className="font-mono text-sm font-semibold">{po.po_number}</span>
                <span
                  className={`rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_STYLES[po.status]}`}
                >
                  {po.status_display}
                </span>
                <span className="text-sm text-zinc-500">{po.supplier_name}</span>
              </div>
              <div className="flex items-center gap-4">
                <div className="text-right text-sm">
                  <div className="font-semibold">{formatPKR(po.total_amount)}</div>
                  <div className="text-xs text-zinc-500">
                    {po.expected_date
                      ? `expected ${formatDate(po.expected_date)}`
                      : `created ${formatDate(po.created_at)}`}
                  </div>
                </div>
                {user?.is_manager && po.status === "draft" && (
                  <button
                    disabled={busyId === po.id}
                    onClick={() => act(po.id, () => purchaseOrders.submit(po.id))}
                    className="rounded-md bg-blue-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-500 disabled:opacity-50"
                  >
                    {busyId === po.id ? "…" : "Submit"}
                  </button>
                )}
                {user?.is_manager &&
                  (po.status === "submitted" ||
                    po.status === "partially_received") && (
                    <button
                      disabled={busyId === po.id}
                      onClick={() => act(po.id, () => purchaseOrders.receive(po.id))}
                      className="rounded-md bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-emerald-500 disabled:opacity-50"
                    >
                      {busyId === po.id ? "…" : "Receive"}
                    </button>
                  )}
              </div>
            </div>

            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-zinc-100 text-left text-xs uppercase tracking-wide text-zinc-500 dark:border-zinc-800">
                  <th className="px-5 py-2 font-medium">Product</th>
                  <th className="px-5 py-2 text-right font-medium">Ordered</th>
                  <th className="px-5 py-2 text-right font-medium">Received</th>
                  <th className="px-5 py-2 text-right font-medium">Unit price</th>
                  <th className="px-5 py-2 text-right font-medium">Line total</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-100 dark:divide-zinc-800">
                {po.lines.map((l) => (
                  <tr key={l.id}>
                    <td className="px-5 py-2">
                      <span className="font-medium">{l.product_name}</span>
                      <span className="ml-2 font-mono text-xs text-zinc-500">
                        {l.product_sku}
                      </span>
                    </td>
                    <td className="px-5 py-2 text-right">{l.quantity_ordered}</td>
                    <td className="px-5 py-2 text-right">{l.quantity_received}</td>
                    <td className="px-5 py-2 text-right">{formatPKR(l.unit_price)}</td>
                    <td className="px-5 py-2 text-right font-medium">
                      {formatPKR(l.line_total)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ))
      )}
    </div>
  );
}
