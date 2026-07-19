"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";

import { suppliers as suppliersApi, supplierProducts } from "@/lib/resources";
import { formatPKR } from "@/lib/format";
import type { Supplier, SupplierProduct } from "@/lib/types";

export default function SupplierDetailPage() {
  const params = useParams<{ id: string }>();
  const supplierId = Number(params.id);
  const [supplier, setSupplier] = useState<Supplier | null>(null);
  const [links, setLinks] = useState<SupplierProduct[]>([]);
  const [notFound, setNotFound] = useState(false);

  useEffect(() => {
    Promise.all([
      suppliersApi.get(supplierId),
      supplierProducts.list({ supplier: supplierId }),
    ])
      .then(([s, sp]) => {
        setSupplier(s);
        setLinks(sp.results);
      })
      .catch(() => setNotFound(true));
  }, [supplierId]);

  if (notFound) return <p className="text-sm text-red-600">Supplier not found.</p>;
  if (!supplier) return <p className="text-sm text-zinc-500">Loading…</p>;

  return (
    <div className="space-y-6">
      <Link href="/suppliers" className="text-sm text-zinc-500 hover:underline">
        ← Back to suppliers
      </Link>

      <div className="rounded-xl border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-900">
        <h2 className="text-xl font-semibold">{supplier.name}</h2>
        <div className="mt-1 font-mono text-sm text-zinc-500">{supplier.code}</div>
        <dl className="mt-5 grid grid-cols-2 gap-4 text-sm sm:grid-cols-3">
          <div>
            <dt className="text-zinc-500">Contact</dt>
            <dd className="font-medium">{supplier.contact_person || "—"}</dd>
          </div>
          <div>
            <dt className="text-zinc-500">Phone</dt>
            <dd className="font-medium">{supplier.phone || "—"}</dd>
          </div>
          <div>
            <dt className="text-zinc-500">Email</dt>
            <dd className="font-medium">{supplier.email || "—"}</dd>
          </div>
          <div>
            <dt className="text-zinc-500">City</dt>
            <dd className="font-medium">{supplier.city || "—"}</dd>
          </div>
          <div>
            <dt className="text-zinc-500">Lead time</dt>
            <dd className="font-medium">{supplier.default_lead_time_days} days</dd>
          </div>
          <div>
            <dt className="text-zinc-500">Payment terms</dt>
            <dd className="font-medium">{supplier.payment_terms || "—"}</dd>
          </div>
        </dl>
      </div>

      <div className="rounded-xl border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
        <div className="border-b border-zinc-200 px-5 py-3 dark:border-zinc-800">
          <h3 className="text-sm font-semibold">Supplied products</h3>
        </div>
        {links.length === 0 ? (
          <p className="px-5 py-6 text-sm text-zinc-500">
            This supplier has no linked products.
          </p>
        ) : (
          <ul className="divide-y divide-zinc-100 dark:divide-zinc-800">
            {links.map((sp) => (
              <li key={sp.id} className="px-5 py-4">
                <div className="flex items-center justify-between">
                  <div>
                    <span className="text-sm font-medium">{sp.product_name}</span>
                    <span className="ml-2 font-mono text-xs text-zinc-500">
                      {sp.product_sku}
                    </span>
                    {sp.is_preferred && (
                      <span className="ml-2 rounded-full bg-indigo-100 px-2 py-0.5 text-xs font-medium text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300">
                        preferred
                      </span>
                    )}
                  </div>
                  <div className="text-xs text-zinc-500">
                    lead {sp.effective_lead_time_days} days
                  </div>
                </div>
                {sp.price_tiers.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-2">
                    {sp.price_tiers.map((t) => (
                      <span
                        key={t.id}
                        className="rounded-md bg-zinc-100 px-2 py-1 text-xs dark:bg-zinc-800"
                      >
                        {t.min_quantity}+ → {formatPKR(t.unit_price)}
                      </span>
                    ))}
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
