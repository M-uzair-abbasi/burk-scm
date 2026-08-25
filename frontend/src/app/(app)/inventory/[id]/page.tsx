"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";

import { StockStatusPill } from "@/components/StockStatusPill";
import { ReorderModal } from "@/components/ReorderModal";
import { useAuth } from "@/components/AuthProvider";
import { ApiError } from "@/lib/api";
import { movements as movementsApi, products } from "@/lib/resources";
import { formatDateTime, formatPKR } from "@/lib/format";
import type { Product, StockMovement } from "@/lib/types";

const REASONS = [
  { value: "adjustment", label: "Manual adjustment" },
  { value: "sale", label: "Sale / dispatch" },
  { value: "return", label: "Customer return" },
  { value: "damage", label: "Damage / write-off" },
];

export default function ProductDetailPage() {
  const params = useParams<{ id: string }>();
  const productId = Number(params.id);
  const router = useRouter();
  const { user } = useAuth();
  const [showReorder, setShowReorder] = useState(false);

  const [product, setProduct] = useState<Product | null>(null);
  const [ledger, setLedger] = useState<StockMovement[]>([]);
  const [notFound, setNotFound] = useState(false);

  const [delta, setDelta] = useState("");
  const [reason, setReason] = useState("adjustment");
  const [note, setNote] = useState("");
  const [allowNegative, setAllowNegative] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const load = useCallback(() => {
    Promise.all([products.get(productId), movementsApi.list(productId)])
      .then(([p, m]) => {
        setProduct(p);
        setLedger(m.results);
      })
      .catch(() => setNotFound(true));
  }, [productId]);

  useEffect(() => {
    load();
  }, [load]);

  async function onAdjust(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    const n = parseInt(delta, 10);
    if (!n) {
      setError("Enter a non-zero quantity (use a minus sign to remove stock).");
      return;
    }
    setSaving(true);
    try {
      await movementsApi.create({
        product: productId,
        quantity_delta: n,
        reason,
        note,
        allow_negative: allowNegative,
      });
      setDelta("");
      setNote("");
      setAllowNegative(false);
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not record the movement.");
    } finally {
      setSaving(false);
    }
  }

  if (notFound) {
    return <p className="text-sm text-red-600">Product not found.</p>;
  }
  if (!product) {
    return <p className="text-sm text-zinc-500">Loading…</p>;
  }

  return (
    <div className="space-y-6">
      <Link href="/inventory" className="text-sm text-zinc-500 hover:underline">
        ← Back to inventory
      </Link>

      {/* Header */}
      <div className="rounded-xl border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-900">
        <div className="flex items-start justify-between">
          <div>
            <div className="flex items-center gap-3">
              <h2 className="text-xl font-semibold">{product.name}</h2>
              <StockStatusPill product={product} />
            </div>
            <div className="mt-1 font-mono text-sm text-zinc-500">
              {product.sku}
              {product.barcode ? ` · ${product.barcode}` : ""}
            </div>
          </div>
          <div className="text-right">
            <div className="text-3xl font-semibold">{product.quantity_on_hand}</div>
            <div className="text-xs text-zinc-500">on hand ({product.unit_display})</div>
            {user?.is_manager && (
              <button
                onClick={() => setShowReorder(true)}
                className="mt-3 rounded-md bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-indigo-500"
              >
                Reorder
              </button>
            )}
          </div>
        </div>

        <dl className="mt-5 grid grid-cols-2 gap-4 text-sm sm:grid-cols-4">
          <div>
            <dt className="text-zinc-500">Category</dt>
            <dd className="font-medium">{product.category_name ?? "—"}</dd>
          </div>
          <div>
            <dt className="text-zinc-500">Safety stock</dt>
            <dd className="font-medium">{product.safety_stock}</dd>
          </div>
          <div>
            <dt className="text-zinc-500">Reorder qty</dt>
            <dd className="font-medium">{product.reorder_quantity}</dd>
          </div>
          <div>
            <dt className="text-zinc-500">Cost price</dt>
            <dd className="font-medium">{formatPKR(product.cost_price)}</dd>
          </div>
        </dl>
      </div>

      {/* Adjust-stock form */}
      <div className="rounded-xl border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-900">
        <h3 className="mb-4 text-sm font-semibold">Adjust stock</h3>
        {error && (
          <div className="mb-4 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950 dark:text-red-300">
            {error}
          </div>
        )}
        <form onSubmit={onAdjust} className="flex flex-wrap items-end gap-3">
          <div>
            <label className="mb-1 block text-xs text-zinc-500">Quantity change</label>
            <input
              type="number"
              value={delta}
              onChange={(e) => setDelta(e.target.value)}
              placeholder="e.g. -5 or 20"
              className="w-32 rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm outline-none focus:border-zinc-900 dark:border-zinc-700 dark:bg-zinc-950"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-zinc-500">Reason</label>
            <select
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              className="rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm outline-none focus:border-zinc-900 dark:border-zinc-700 dark:bg-zinc-950"
            >
              {REASONS.map((r) => (
                <option key={r.value} value={r.value}>
                  {r.label}
                </option>
              ))}
            </select>
          </div>
          <div className="flex-1">
            <label className="mb-1 block text-xs text-zinc-500">
              Note{allowNegative ? " (required for override)" : " (optional)"}
            </label>
            <input
              type="text"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              className="w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm outline-none focus:border-zinc-900 dark:border-zinc-700 dark:bg-zinc-950"
            />
          </div>
          {user?.is_manager && (
            <label className="flex items-center gap-2 pb-2 text-xs text-zinc-500">
              <input
                type="checkbox"
                checked={allowNegative}
                onChange={(e) => setAllowNegative(e.target.checked)}
                className="h-4 w-4"
              />
              Allow below zero
            </label>
          )}
          <button
            type="submit"
            disabled={saving}
            className="rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-zinc-700 disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-300"
          >
            {saving ? "Saving…" : "Record"}
          </button>
        </form>
      </div>

      {/* Ledger */}
      <div className="overflow-x-auto rounded-xl border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
        <div className="border-b border-zinc-200 px-5 py-3 dark:border-zinc-800">
          <h3 className="text-sm font-semibold">Movement ledger</h3>
        </div>
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-zinc-200 text-left text-xs uppercase tracking-wide text-zinc-500 dark:border-zinc-800">
              <th className="px-4 py-2 font-medium">When</th>
              <th className="px-4 py-2 font-medium">Reason</th>
              <th className="px-4 py-2 text-right font-medium">Change</th>
              <th className="px-4 py-2 font-medium">By</th>
              <th className="px-4 py-2 font-medium">Note / PO</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-100 dark:divide-zinc-800">
            {ledger.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-4 py-6 text-center text-zinc-500">
                  No movements yet.
                </td>
              </tr>
            ) : (
              ledger.map((m) => (
                <tr key={m.id}>
                  <td className="px-4 py-2 text-zinc-500">
                    {formatDateTime(m.created_at)}
                  </td>
                  <td className="px-4 py-2">{m.reason_display}</td>
                  <td
                    className={`px-4 py-2 text-right font-mono font-medium ${
                      m.quantity_delta >= 0
                        ? "text-emerald-600 dark:text-emerald-400"
                        : "text-red-600 dark:text-red-400"
                    }`}
                  >
                    {m.quantity_delta > 0 ? `+${m.quantity_delta}` : m.quantity_delta}
                  </td>
                  <td className="px-4 py-2 text-zinc-500">
                    {m.created_by_username ?? "—"}
                  </td>
                  <td className="px-4 py-2 text-zinc-500">
                    {m.purchase_order ? (
                      <Link
                        href="/purchase-orders"
                        className="text-indigo-600 hover:underline dark:text-indigo-400"
                      >
                        PO #{m.purchase_order}
                      </Link>
                    ) : (
                      m.note || "—"
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {showReorder && (
        <ReorderModal
          product={product}
          onClose={() => setShowReorder(false)}
          onCreated={() => {
            setShowReorder(false);
            router.push("/purchase-orders");
          }}
        />
      )}
    </div>
  );
}
