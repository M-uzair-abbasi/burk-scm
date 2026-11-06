"use client";

import { useEffect, useMemo, useState } from "react";
import { TriangleAlert } from "lucide-react";

import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { Input } from "@/components/ui/Input";
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
    let alive = true;
    supplierProducts.list({ product: product.id }).then((r) => {
      if (!alive) return;
      const links = r.results.filter((s) => s.is_active);
      setPreferred(links.find((s) => s.is_preferred) ?? links[0] ?? null);
      setLoaded(true);
    });
    return () => {
      alive = false;
    };
  }, [product.id]);

  const unitPrice = useMemo(
    () => (preferred ? resolveUnitPrice(preferred, quantity) : null),
    [preferred, quantity],
  );
  const lineTotal = unitPrice !== null ? Number(unitPrice) * quantity : null;

  async function onSubmit() {
    setError(null);
    setSubmitting(true);
    try {
      const po = await purchaseOrders.reorder({
        product: product.id,
        quantity,
      });
      onCreated(po.id);
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Could not create the order.",
      );
      setSubmitting(false);
    }
  }

  return (
    <Dialog
      open
      onOpenChange={(next) => {
        if (!next) onClose();
      }}
      title={`Reorder ${product.name}`}
      description={product.sku}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button
            variant="primary"
            onClick={onSubmit}
            disabled={!preferred || unitPrice === null || submitting}
          >
            {submitting ? "Creating…" : "Create draft PO"}
          </Button>
        </>
      }
    >
      {!loaded ? (
        <p className="text-sm text-secondary">Loading supplier…</p>
      ) : !preferred ? (
        <div className="flex gap-2 rounded-lg border border-warning/30 bg-warning-soft px-3 py-2.5 text-sm text-warning-text">
          <TriangleAlert aria-hidden className="mt-0.5 size-4 shrink-0" />
          <span>
            No supplier is linked to this product, so it cannot be reordered
            from here. Link one on the supplier record first.
          </span>
        </div>
      ) : (
        <div className="flex flex-col gap-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <div className="eyebrow text-muted">Supplier</div>
              <div className="mt-1.5 text-sm font-medium text-primary">
                {preferred.supplier_name}
              </div>
            </div>
            <div>
              <div className="eyebrow text-muted">Lead time</div>
              <div className="mt-1.5 text-sm font-medium text-primary">
                {preferred.effective_lead_time_days} days
              </div>
            </div>
          </div>

          <div>
            <label
              htmlFor="reorder-qty"
              className="eyebrow mb-1.5 block text-muted"
            >
              Quantity
            </label>
            <Input
              id="reorder-qty"
              type="number"
              min={1}
              value={quantity}
              onChange={(e) =>
                setQuantity(Math.max(1, Number(e.target.value)))
              }
              className="tabular w-32 font-mono"
            />
          </div>

          <div className="rounded-lg bg-sunken p-3 text-sm">
            <div className="flex justify-between">
              <span className="text-secondary">Unit price</span>
              <span className="tabular font-mono font-medium text-primary">
                {unitPrice !== null ? formatPKR(unitPrice) : "No matching tier"}
              </span>
            </div>
            <div className="mt-1.5 flex justify-between">
              <span className="text-secondary">Order total</span>
              <span className="tabular font-mono font-semibold text-primary">
                {lineTotal !== null ? formatPKR(lineTotal) : "—"}
              </span>
            </div>
            {unitPrice === null ? (
              <p className="mt-2 text-xs text-warning-text">
                This quantity is below the supplier&rsquo;s lowest price tier.
                Raise it to reach a tier.
              </p>
            ) : null}
          </div>

          {error ? (
            <div className="rounded-lg border border-critical/30 bg-critical-soft px-3 py-2 text-sm text-critical-text">
              {error}
            </div>
          ) : null}
        </div>
      )}
    </Dialog>
  );
}
