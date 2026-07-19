"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

import { StockStatusPill } from "@/components/StockStatusPill";
import { dashboard, products } from "@/lib/resources";
import { formatNumber } from "@/lib/format";
import type { DashboardSummary, Product } from "@/lib/types";

function Card({
  label,
  value,
  tone = "default",
}: {
  label: string;
  value: number;
  tone?: "default" | "warn" | "danger";
}) {
  const toneCls =
    tone === "danger"
      ? "text-red-600 dark:text-red-400"
      : tone === "warn"
        ? "text-amber-600 dark:text-amber-400"
        : "text-zinc-900 dark:text-zinc-100";
  return (
    <div className="rounded-xl border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-900">
      <div className="text-sm text-zinc-500">{label}</div>
      <div className={`mt-1 text-3xl font-semibold ${toneCls}`}>
        {formatNumber(value)}
      </div>
    </div>
  );
}

export default function DashboardPage() {
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [lowStock, setLowStock] = useState<Product[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([dashboard.summary(), products.list({ low_stock: true })])
      .then(([s, low]) => {
        setSummary(s);
        setLowStock(low.results);
      })
      .catch(() => setError("Could not load the dashboard."));
  }, []);

  if (error) {
    return <p className="text-sm text-red-600">{error}</p>;
  }
  if (!summary) {
    return <p className="text-sm text-zinc-500">Loading…</p>;
  }

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card label="Total SKUs" value={summary.total_skus} />
        <Card label="Low stock" value={summary.low_stock_count} tone="warn" />
        <Card
          label="Out of stock"
          value={summary.out_of_stock_count}
          tone="danger"
        />
        <Card label="Open purchase orders" value={summary.open_po_count} />
      </div>

      <div className="rounded-xl border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
        <div className="flex items-center justify-between border-b border-zinc-200 px-5 py-3 dark:border-zinc-800">
          <h2 className="text-sm font-semibold">Low-stock items</h2>
          <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-800 dark:bg-amber-950 dark:text-amber-300">
            {lowStock.length}
          </span>
        </div>

        {lowStock.length === 0 ? (
          <p className="px-5 py-6 text-sm text-zinc-500">
            Nothing below its safety threshold. All good.
          </p>
        ) : (
          <ul className="divide-y divide-zinc-100 dark:divide-zinc-800">
            {lowStock.map((p) => (
              <li key={p.id}>
                <Link
                  href={`/inventory/${p.id}`}
                  className="flex items-center justify-between px-5 py-3 transition-colors hover:bg-zinc-50 dark:hover:bg-zinc-800/50"
                >
                  <div>
                    <div className="text-sm font-medium">{p.name}</div>
                    <div className="font-mono text-xs text-zinc-500">{p.sku}</div>
                  </div>
                  <div className="flex items-center gap-4">
                    <div className="text-right text-sm">
                      <span className="font-medium">{p.quantity_on_hand}</span>
                      <span className="text-zinc-400"> / {p.safety_stock}</span>
                    </div>
                    <StockStatusPill product={p} />
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
