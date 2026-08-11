"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";

import { ChannelBadge } from "@/components/ChannelBadge";
import { OrderStatusPill } from "@/components/OrderStatusPill";
import { ApiError } from "@/lib/api";
import { orders as ordersApi, shipments } from "@/lib/resources";
import { formatDateTime, formatPKR } from "@/lib/format";
import type { SalesOrder } from "@/lib/types";

export default function OrderDetailPage() {
  const params = useParams<{ id: string }>();
  const id = Number(params.id);
  const [order, setOrder] = useState<SalesOrder | null>(null);
  const [loading, setLoading] = useState(true);
  const [showRaw, setShowRaw] = useState(false);
  const [shipBusy, setShipBusy] = useState(false);
  const [shipError, setShipError] = useState<string | null>(null);

  useEffect(() => {
    ordersApi
      .get(id)
      .then(setOrder)
      .finally(() => setLoading(false));
  }, [id]);

  // Demo stand-in for a real courier webhook (Module 5); DELIVERED also
  // triggers Module 6's scheduled review reminder server-side.
  async function advanceShipment(status: "in_transit" | "delivered") {
    if (!order?.shipment) return;
    setShipBusy(true);
    setShipError(null);
    try {
      await shipments.advance(order.shipment.id, status);
      // Re-fetch rather than merge: DELIVERED also flips order.status and
      // creates a new (scheduled) review-request notification server-side.
      setOrder(await ordersApi.get(id));
    } catch (err) {
      setShipError(err instanceof ApiError ? err.message : "Could not advance shipment.");
    } finally {
      setShipBusy(false);
    }
  }

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

      {/* Module 5: courier booking + tracking */}
      {order.shipment && (
        <div className="rounded-xl border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-900">
          <h3 className="mb-3 text-xs font-semibold uppercase tracking-wide text-zinc-500">
            Shipment
          </h3>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="text-sm">
              <span className="font-medium">{order.shipment.courier_display}</span>
              <span className="ml-2 font-mono text-zinc-500">
                {order.shipment.tracking_number}
              </span>
              <span className="ml-3 rounded-full bg-zinc-100 px-2 py-0.5 text-xs font-medium text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300">
                {order.shipment.status_display}
              </span>
            </div>
            <div className="flex gap-2">
              {order.shipment.status === "booked" && (
                <button
                  disabled={shipBusy}
                  onClick={() => advanceShipment("in_transit")}
                  className="rounded-md border border-zinc-300 px-3 py-1.5 text-xs font-medium hover:bg-zinc-100 disabled:opacity-40 dark:border-zinc-700 dark:hover:bg-zinc-800"
                >
                  Simulate: mark in transit
                </button>
              )}
              {order.shipment.status === "in_transit" && (
                <button
                  disabled={shipBusy}
                  onClick={() => advanceShipment("delivered")}
                  className="rounded-md border border-emerald-300 px-3 py-1.5 text-xs font-medium text-emerald-700 hover:bg-emerald-50 disabled:opacity-40 dark:border-emerald-900 dark:text-emerald-300 dark:hover:bg-emerald-950"
                >
                  Simulate: mark delivered
                </button>
              )}
            </div>
          </div>
          {shipError && (
            <p className="mt-2 text-sm text-red-600 dark:text-red-400">{shipError}</p>
          )}
          <ul className="mt-3 space-y-1 border-t border-zinc-100 pt-3 text-xs text-zinc-500 dark:border-zinc-800">
            {order.shipment.events.map((e) => (
              <li key={e.id}>
                {formatDateTime(e.occurred_at)} — {e.status_display}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Module 4/5/6: customer dispatch history */}
      {(order.notifications ?? []).length > 0 && (
        <div className="overflow-hidden rounded-xl border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
          <div className="border-b border-zinc-200 px-4 py-3 text-xs font-semibold uppercase tracking-wide text-zinc-500 dark:border-zinc-800">
            Customer notifications
          </div>
          <ul className="divide-y divide-zinc-100 dark:divide-zinc-800">
            {(order.notifications ?? []).map((n) => (
              <li
                key={n.id}
                className="flex flex-wrap items-center justify-between gap-2 px-4 py-3 text-sm"
              >
                <div>
                  <span className="font-medium">{n.kind_display}</span>
                  <span className="ml-2 text-zinc-500">
                    via {n.channel_display} → {n.recipient || "—"}
                  </span>
                </div>
                <div className="flex items-center gap-3">
                  {n.status === "sent" && (
                    <span className="text-xs text-zinc-500">
                      {n.latency_seconds !== null
                        ? `${n.latency_seconds.toFixed(1)}s latency`
                        : formatDateTime(n.sent_at)}
                    </span>
                  )}
                  {n.status === "scheduled" && n.scheduled_for && (
                    <span className="text-xs text-zinc-500">
                      due {formatDateTime(n.scheduled_for)}
                    </span>
                  )}
                  <span
                    className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                      n.status === "sent"
                        ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300"
                        : n.status === "failed"
                          ? "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300"
                          : "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300"
                    }`}
                  >
                    {n.status_display}
                  </span>
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}

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
