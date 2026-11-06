"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, History, SlidersHorizontal, TriangleAlert } from "lucide-react";

import { ReorderModal } from "@/components/ReorderModal";
import { useAuth } from "@/components/AuthProvider";
import { Button, ButtonLink } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Input } from "@/components/ui/Input";
import { Meter } from "@/components/ui/Meter";
import { Panel } from "@/components/ui/Panel";
import { Select } from "@/components/ui/Select";
import { StatusPill } from "@/components/ui/StatusPill";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/Table";
import { Term } from "@/components/ui/Tooltip";
import { cn } from "@/components/ui/cn";
import { stockLabel, stockTone } from "@/components/ui/status";
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
  const [reloadToken, setReloadToken] = useState(0);

  const [delta, setDelta] = useState("");
  const [reason, setReason] = useState("adjustment");
  const [note, setNote] = useState("");
  const [allowNegative, setAllowNegative] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let alive = true;
    Promise.all([products.get(productId), movementsApi.list(productId)])
      .then(([p, m]) => {
        if (!alive) return;
        setProduct(p);
        setLedger(m.results);
      })
      .catch(() => {
        if (alive) setNotFound(true);
      });
    return () => {
      alive = false;
    };
  }, [productId, reloadToken]);

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
      setReloadToken((t) => t + 1);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Could not record the movement.",
      );
    } finally {
      setSaving(false);
    }
  }

  if (notFound) {
    return (
      <div className="py-12 text-center">
        <p className="text-sm text-secondary">That product could not be found.</p>
        <ButtonLink href="/inventory" variant="secondary" className="mt-4">
          Back to inventory
        </ButtonLink>
      </div>
    );
  }
  if (!product) {
    return <p className="py-12 text-center text-sm text-secondary">Loading…</p>;
  }

  const tone = stockTone(product.quantity_on_hand, product.safety_stock);

  return (
    <div className="flex flex-col gap-5">
      <div>
        <Link
          href="/inventory"
          className="inline-flex items-center gap-1.5 text-sm text-secondary transition-colors duration-150 hover:text-primary"
        >
          <ArrowLeft aria-hidden className="size-3.5" />
          Back to inventory
        </Link>
      </div>

      <Panel bodyClassName="p-5">
        <div className="flex flex-wrap items-start justify-between gap-5">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2.5">
              <h1 className="text-xl font-semibold tracking-tight text-primary">
                {product.name}
              </h1>
              <StatusPill
                tone={tone}
                variant={tone === "critical" ? "solid" : "soft"}
              >
                {stockLabel(product.quantity_on_hand, product.safety_stock)}
              </StatusPill>
            </div>
            <div className="tabular mt-1 font-mono text-sm text-muted">
              {product.sku}
              {product.barcode ? ` · ${product.barcode}` : " · no barcode"}
            </div>
          </div>

          <div className="text-right">
            <div
              className={cn(
                "tabular text-3xl font-semibold leading-none",
                tone === "critical"
                  ? "text-critical"
                  : tone === "warning"
                    ? "text-warning"
                    : "text-primary",
              )}
            >
              {product.quantity_on_hand}
            </div>
            <div className="mt-1 text-xs text-muted">
              on hand ({product.unit_display})
            </div>
            <div className="mt-2 w-32">
              <Meter
                value={product.quantity_on_hand}
                max={Math.max(product.safety_stock, 1)}
                tone={tone}
                label="Stock against safety level"
              />
            </div>
            {user?.is_manager ? (
              <Button
                size="sm"
                variant="primary"
                className="mt-3"
                onClick={() => setShowReorder(true)}
              >
                Reorder
              </Button>
            ) : null}
          </div>
        </div>

        <dl className="mt-6 grid grid-cols-2 gap-5 border-t border-subtle pt-5 sm:grid-cols-4">
          <div>
            <dt className="eyebrow text-muted">Category</dt>
            <dd className="mt-1.5 text-sm font-medium text-primary">
              {product.category_name ?? "—"}
            </dd>
          </div>
          <div>
            <dt className="eyebrow text-muted">
              <Term definition="The level you never want stock to fall under. Reaching it flags the product for reorder.">
                Safety stock
              </Term>
            </dt>
            <dd className="tabular mt-1.5 text-sm font-medium text-primary">
              {product.safety_stock}
            </dd>
          </div>
          <div>
            <dt className="eyebrow text-muted">Reorder qty</dt>
            <dd className="tabular mt-1.5 text-sm font-medium text-primary">
              {product.reorder_quantity}
            </dd>
          </div>
          <div>
            <dt className="eyebrow text-muted">Cost price</dt>
            <dd className="tabular mt-1.5 text-sm font-medium text-primary">
              {formatPKR(product.cost_price)}
            </dd>
          </div>
        </dl>
      </Panel>

      <Panel
        eyebrow="Correction"
        title="Adjust stock"
        description="Packing and receiving move stock on their own — use this only to correct a count."
        icon={SlidersHorizontal}
        bodyClassName="p-5"
      >
        {error ? (
          <div className="mb-4 flex items-center gap-2 rounded-lg border border-critical/30 bg-critical-soft px-3 py-2 text-sm text-critical-text">
            <TriangleAlert aria-hidden className="size-4 shrink-0" />
            {error}
          </div>
        ) : null}

        <form onSubmit={onAdjust} className="flex flex-wrap items-end gap-3">
          <div>
            <label htmlFor="delta" className="eyebrow mb-1.5 block text-muted">
              Quantity change
            </label>
            <Input
              id="delta"
              type="number"
              value={delta}
              onChange={(e) => setDelta(e.target.value)}
              placeholder="-5 or 20"
              className="tabular w-32 font-mono"
            />
          </div>
          <div>
            <span className="eyebrow mb-1.5 block text-muted">Reason</span>
            <Select
              value={reason}
              onValueChange={setReason}
              options={REASONS}
              ariaLabel="Reason for adjustment"
            />
          </div>
          <div className="min-w-48 flex-1">
            <label htmlFor="note" className="eyebrow mb-1.5 block text-muted">
              Note{allowNegative ? " (required for override)" : " (optional)"}
            </label>
            <Input
              id="note"
              type="text"
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />
          </div>
          {user?.is_manager ? (
            <label
              className={cn(
                "inline-flex h-9 cursor-pointer select-none items-center gap-2 rounded-md border px-3 text-sm transition-colors duration-150",
                allowNegative
                  ? "border-warning/50 bg-warning-soft text-warning-text"
                  : "border-strong bg-raised text-secondary hover:border-accent/50",
              )}
            >
              <input
                type="checkbox"
                checked={allowNegative}
                onChange={(e) => setAllowNegative(e.target.checked)}
                className="size-3.5 accent-current"
              />
              Allow below zero
            </label>
          ) : null}
          <Button type="submit" variant="primary" disabled={saving}>
            {saving ? "Saving…" : "Record movement"}
          </Button>
        </form>
      </Panel>

      <Panel
        eyebrow="Audit trail"
        title="Movement ledger"
        description="Every change to this product's stock, and what caused it."
        icon={History}
        bodyClassName={ledger.length === 0 ? "p-5" : "p-0"}
      >
        {ledger.length === 0 ? (
          <EmptyState
            icon={History}
            title="No movements recorded yet"
            body="Stock movements appear here as soon as this product is packed into an order, received on a purchase order, or corrected above."
          />
        ) : (
          <Table>
            <THead>
              <TH>When</TH>
              <TH>Reason</TH>
              <TH align="right">Change</TH>
              <TH>By</TH>
              <TH>Note / PO</TH>
            </THead>
            <TBody>
              {ledger.map((m) => (
                <TR key={m.id}>
                  <TD className="whitespace-nowrap text-xs text-secondary">
                    {formatDateTime(m.created_at)}
                  </TD>
                  <TD>{m.reason_display}</TD>
                  <TD
                    align="right"
                    mono
                    className={cn(
                      "font-semibold",
                      m.quantity_delta >= 0 ? "text-success" : "text-critical",
                    )}
                  >
                    {m.quantity_delta > 0
                      ? `+${m.quantity_delta}`
                      : m.quantity_delta}
                  </TD>
                  <TD className="text-secondary">
                    {m.created_by_username ?? "—"}
                  </TD>
                  <TD className="text-secondary">
                    {m.purchase_order ? (
                      <Link
                        href="/purchase-orders"
                        className="text-accent-text hover:underline"
                      >
                        PO #{m.purchase_order}
                      </Link>
                    ) : (
                      m.note || "—"
                    )}
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
        )}
      </Panel>

      {showReorder ? (
        <ReorderModal
          product={product}
          onClose={() => setShowReorder(false)}
          onCreated={() => {
            setShowReorder(false);
            router.push("/purchase-orders");
          }}
        />
      ) : null}
    </div>
  );
}
