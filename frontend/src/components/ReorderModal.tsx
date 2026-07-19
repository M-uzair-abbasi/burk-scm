"use client";

import { useEffect, useMemo, useState } from "react";

import { ApiError } from "@/lib/api";
import { purchaseOrders, supplierProducts } from "@/lib/resources";
import { formatPKR } from "@/lib/format";
import type { Product, SupplierProduct } from "@/lib/types";

/** Highest tier whose minimum the quantity reaches; null if below every tier. */
function resolveUnitPrice(sp: SupplierProduct, quantity: number): string | null {
  const eligible = sp.price_tiers
    .filter((t) => t.min_quantity <= quantity)
    .sort((a, b) => b.min_quantity - a.min_quantity);
  return eligible.length ? eligible[0].unit_price : null;
}

export function ReorderModal({
  product,
  onClose,
  onCreated,
}: {
  product: Product;
  onClose: () => void;
  onCreated: (poId: number) => void;
}) {
  const [preferred, setPreferred] = useState<SupplierProduct | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [quantity, setQuantity] = useState(product.reorder_quantity || 1);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    supplierProducts.list({ product: product.id }).then((r) => {
      const links = r.results.filter((s) => s.is_active);
      setPreferred(links.find((s) => s.is_preferred) ?? links[0] ?? null);
      setLoaded(true);
    });
  }, [product.id]);

  const unitPrice = useMemo(
    () => (preferred ? resolveUnitPrice(preferred, quantity) : null),
    [preferred, quantity],
  );
  const lineTotal =
    unitPrice !== null ? Number(unitPrice) * quantity : null;

  async function onSubmit() {
    setError(null);
    setSubmitting(true);
    try {
      const po = await purchaseOrders.reorder({ product: product.id, quantity });
      onCreated(po.id);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not create the order.");
      setSubmitting(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-md rounded-xl border border-zinc-200 bg-white p-6 shadow-xl dark:border-zinc-800 dark:bg-zinc-900"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="text-base font-semibold">Reorder {product.name}</h3>
        <p className="mt-1 font-mono text-xs text-zinc-500">{product.sku}</p>

        {!loaded ? (
          <p className="mt-6 text-sm text-zinc-500">Loading supplier…</p>
        ) : !preferred ? (
          <div className="mt-6 rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:bg-amber-950 dark:text-amber-300">
            No supplier is linked to this product, so it can&apos;t be reordered
            from here. Add a supplier first.
          </div>
        ) : (
          <div className="mt-5 space-y-4">
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <div className="text-zinc-500">Supplier</div>
                <div className="font-medium">{preferred.supplier_name}</div>
              </div>
              <div>
                <div className="text-zinc-500">Lead time</div>
                <div className="font-medium">
                  {preferred.effective_lead_time_days} days
                </div>
              </div>
            </div>

            <div>
              <label className="mb-1 block text-xs text-zinc-500">Quantity</label>
              <input
                type="number"
                min={1}
                value={quantity}
                onChange={(e) => setQuantity(Math.max(1, Number(e.target.value)))}
                className="w-32 rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm outline-none focus:border-zinc-900 dark:border-zinc-700 dark:bg-zinc-950"
              />
            </div>

            <div className="rounded-md bg-zinc-50 p-3 text-sm dark:bg-zinc-800/50">
              <div className="flex justify-between">
                <span className="text-zinc-500">Unit price</span>
                <span className="font-medium">
                  {unitPrice !== null ? formatPKR(unitPrice) : "No matching tier"}
                </span>
              </div>
              <div className="mt-1 flex justify-between">
                <span className="text-zinc-500">Order total</span>
                <span className="font-semibold">
                  {lineTotal !== null ? formatPKR(lineTotal) : "—"}
                </span>
              </div>
            </div>

            {error && (
              <div className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950 dark:text-red-300">
                {error}
              </div>
            )}
          </div>
        )}

        <div className="mt-6 flex justify-end gap-2">
          <button
            onClick={onClose}
            className="rounded-md border border-zinc-300 px-4 py-2 text-sm font-medium text-zinc-700 hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-800"
          >
            Cancel
          </button>
          <button
            onClick={onSubmit}
            disabled={!preferred || unitPrice === null || submitting}
            className="rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-700 disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-300"
          >
            {submitting ? "Creating…" : "Create draft PO"}
          </button>
        </div>
      </div>
    </div>
  );
}
