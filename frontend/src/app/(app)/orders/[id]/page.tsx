"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";

import { ChannelBadge } from "@/components/ChannelBadge";
import { OrderStatusPill } from "@/components/OrderStatusPill";
import { orders as ordersApi } from "@/lib/resources";
import { formatDateTime, formatPKR } from "@/lib/format";
import type { SalesOrder } from "@/lib/types";

export default function OrderDetailPage() {
  const params = useParams<{ id: string }>();
  const id = Number(params.id);
  const [order, setOrder] = useState<SalesOrder | null>(null);
  const [loading, setLoading] = useState(true);
  const [showRaw, setShowRaw] = useState(false);

  useEffect(() => {
    ordersApi
      .get(id)
      .then(setOrder)
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) return <p className="text-sm text-zinc-500">Loading…</p>;
  if (!order) return <p className="text-sm text-zinc-500">Order not found.</p>;

  return (
    <div className="space-y-5">
      <Link
        href="/orders"
        className="inline-block text-sm text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100"
      >
        ← Back to queue
      </Link>

      {/* Header */}
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="font-mono text-lg font-semibold">{order.reference}</h2>
        <ChannelBadge channel={order.channel} label={order.channel_display} />
        <OrderStatusPill status={order.status} label={order.status_display} />
        <span className="font-mono text-sm text-zinc-500">
          {order.channel_display} · {order.external_id}
        </span>
      </div>

      <div className="grid gap-5 lg:grid-cols-3">
        {/* Customer */}
        <div className="rounded-xl border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-900">
          <h3 className="mb-3 text-xs font-semibold uppercase tracking-wide text-zinc-500">
            Customer
          </h3>
          <dl className="space-y-2 text-sm">
            <div>
              <dt className="text-xs text-zinc-500">Name</dt>
              <dd className="font-medium">{order.customer_name || "—"}</dd>
            </div>
            <div>
              <dt className="text-xs text-zinc-500">Phone</dt>
              <dd>{order.customer_phone || "—"}</dd>
            </div>
            <div>
              <dt className="text-xs text-zinc-500">Email</dt>
              <dd>{order.customer_email || "—"}</dd>
            </div>
            <div>
              <dt className="text-xs text-zinc-500">Ship to</dt>
              <dd>{order.shipping_address || "—"}</dd>
            </div>
          </dl>
        </div>

        {/* Timeline / sync */}
        <div className="rounded-xl border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-900">
          <h3 className="mb-3 text-xs font-semibold uppercase tracking-wide text-zinc-500">
            Timeline
          </h3>
          <dl className="space-y-2 text-sm">
            <div>
              <dt className="text-xs text-zinc-500">Placed on channel</dt>
              <dd>{formatDateTime(order.placed_at)}</dd>
            </div>
            <div>
              <dt className="text-xs text-zinc-500">First ingested</dt>
              <dd>{formatDateTime(order.ingested_at)}</dd>
            </div>
            <div>
              <dt className="text-xs text-zinc-500">Last synced</dt>
              <dd>{formatDateTime(order.last_synced_at)}</dd>
            </div>
          </dl>
        </div>

        {/* Totals */}
        <div className="rounded-xl border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-900">
          <h3 className="mb-3 text-xs font-semibold uppercase tracking-wide text-zinc-500">
            Totals
          </h3>
          <dl className="space-y-2 text-sm">
            <div className="flex justify-between">
              <dt className="text-zinc-500">Subtotal</dt>
              <dd>{formatPKR(order.subtotal)}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-zinc-500">Shipping</dt>
              <dd>{formatPKR(order.shipping_fee)}</dd>
            </div>
            <div className="flex justify-between border-t border-zinc-200 pt-2 font-semibold dark:border-zinc-800">
              <dt>Total</dt>
              <dd>{formatPKR(order.total)}</dd>
            </div>
          </dl>
        </div>
      </div>

      {/* Lines */}
      <div className="overflow-x-auto rounded-xl border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-zinc-200 text-left text-xs uppercase tracking-wide text-zinc-500 dark:border-zinc-800">
              <th className="px-4 py-3 font-medium">SKU</th>
              <th className="px-4 py-3 font-medium">Product</th>
              <th className="px-4 py-3 text-right font-medium">Qty</th>
              <th className="px-4 py-3 text-right font-medium">Unit price</th>
              <th className="px-4 py-3 text-right font-medium">Line total</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-100 dark:divide-zinc-800">
            {(order.lines ?? []).map((l) => (
              <tr key={l.id}>
                <td className="px-4 py-3 font-mono text-xs">{l.sku || "—"}</td>
                <td className="px-4 py-3">
                  {l.product ? (
                    <Link
                      href={`/inventory/${l.product}`}
                      className="font-medium text-indigo-600 hover:underline dark:text-indigo-400"
                    >
                      {l.product_name}
                    </Link>
                  ) : (
                    <span className="font-medium">
                      {l.product_name}
                      <span className="ml-2 rounded bg-amber-100 px-1.5 py-0.5 text-xs text-amber-800 dark:bg-amber-950 dark:text-amber-300">
                        unstocked SKU
                      </span>
                    </span>
                  )}
                </td>
                <td className="px-4 py-3 text-right tabular-nums">{l.quantity}</td>
                <td className="px-4 py-3 text-right">{formatPKR(l.unit_price)}</td>
                <td className="px-4 py-3 text-right font-medium">
                  {formatPKR(l.line_total)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Raw payload (audit) */}
      <div className="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
        <button
          onClick={() => setShowRaw((v) => !v)}
          className="text-sm font-medium text-zinc-600 hover:text-zinc-900 dark:text-zinc-300 dark:hover:text-zinc-100"
        >
          {showRaw ? "▾" : "▸"} Raw channel payload
        </button>
        {showRaw && (
          <pre className="mt-3 overflow-x-auto rounded-lg bg-zinc-50 p-3 text-xs text-zinc-700 dark:bg-zinc-950 dark:text-zinc-300">
            {JSON.stringify(order.raw_payload ?? {}, null, 2)}
          </pre>
        )}
      </div>
    </div>
  );
}
