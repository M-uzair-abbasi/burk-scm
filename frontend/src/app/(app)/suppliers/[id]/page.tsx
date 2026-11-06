"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, PackageSearch } from "lucide-react";

import { ButtonLink } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Panel } from "@/components/ui/Panel";
import { StatusPill } from "@/components/ui/StatusPill";
import { Term } from "@/components/ui/Tooltip";
import { suppliers as suppliersApi, supplierProducts } from "@/lib/resources";
import { formatPKR } from "@/lib/format";
import type { Supplier, SupplierProduct } from "@/lib/types";

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="eyebrow text-muted">{label}</dt>
      <dd className="mt-1.5 text-sm font-medium text-primary">{value}</dd>
    </div>
  );
}

export default function SupplierDetailPage() {
  const params = useParams<{ id: string }>();
  const supplierId = Number(params.id);
  const [supplier, setSupplier] = useState<Supplier | null>(null);
  const [links, setLinks] = useState<SupplierProduct[]>([]);
  const [notFound, setNotFound] = useState(false);

  useEffect(() => {
    let alive = true;
    Promise.all([
      suppliersApi.get(supplierId),
      supplierProducts.list({ supplier: supplierId }),
    ])
      .then(([s, sp]) => {
        if (!alive) return;
        setSupplier(s);
        setLinks(sp.results);
      })
      .catch(() => {
        if (alive) setNotFound(true);
      });
    return () => {
      alive = false;
    };
  }, [supplierId]);

  if (notFound) {
    return (
      <div className="py-12 text-center">
        <p className="text-sm text-secondary">That supplier could not be found.</p>
        <ButtonLink href="/suppliers" variant="secondary" className="mt-4">
          Back to suppliers
        </ButtonLink>
      </div>
    );
  }
  if (!supplier) {
    return (
      <p className="py-12 text-center text-sm text-secondary">Loading…</p>
    );
  }

  return (
    <div className="flex flex-col gap-5">
      <div>
        <Link
          href="/suppliers"
          className="inline-flex items-center gap-1.5 text-sm text-secondary transition-colors duration-150 hover:text-primary"
        >
          <ArrowLeft aria-hidden className="size-3.5" />
          Back to suppliers
        </Link>
        <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-2">
          <h1 className="text-xl font-semibold tracking-tight text-primary">
            {supplier.name}
          </h1>
          <span className="tabular font-mono text-sm text-muted">
            {supplier.code}
          </span>
        </div>
      </div>

      <Panel eyebrow="Contact" title="How to reach them" bodyClassName="p-5">
        <dl className="grid grid-cols-2 gap-5 sm:grid-cols-3">
          <Field label="Contact" value={supplier.contact_person || "—"} />
          <Field label="Phone" value={supplier.phone || "—"} />
          <Field label="Email" value={supplier.email || "—"} />
          <Field label="City" value={supplier.city || "—"} />
          <Field
            label="Lead time"
            value={`${supplier.default_lead_time_days} days`}
          />
          <Field label="Payment terms" value={supplier.payment_terms || "—"} />
        </dl>
      </Panel>

      <Panel
        eyebrow="Catalogue"
        title={`Supplied products (${links.length})`}
        bodyClassName={links.length === 0 ? "p-5" : "divide-y divide-subtle"}
      >
        {links.length === 0 ? (
          <EmptyState
            icon={PackageSearch}
            title="No products linked to this supplier"
            body="Linking a product here is what makes it reorderable from the inventory screen, with this supplier's lead time and pricing applied."
            action={
              <ButtonLink href="/inventory" variant="secondary">
                Browse inventory
              </ButtonLink>
            }
          />
        ) : (
          links.map((sp) => (
            <div key={sp.id} className="px-5 py-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm font-medium text-primary">
                    {sp.product_name}
                  </span>
                  <span className="tabular font-mono text-xs text-muted">
                    {sp.product_sku}
                  </span>
                  {sp.is_preferred ? (
                    <StatusPill tone="success" variant="soft">
                      Preferred
                    </StatusPill>
                  ) : null}
                </div>
                <span className="text-xs text-secondary">
                  lead {sp.effective_lead_time_days} days
                </span>
              </div>
              {sp.price_tiers.length > 0 ? (
                <div className="mt-2.5 flex flex-wrap gap-1.5">
                  {sp.price_tiers.map((t) => (
                    <span
                      key={t.id}
                      className="tabular rounded-md bg-sunken px-2 py-1 font-mono text-xs text-secondary"
                    >
                      {t.min_quantity}+ → {formatPKR(t.unit_price)}
                    </span>
                  ))}
                </div>
              ) : null}
            </div>
          ))
        )}
      </Panel>

      <p className="text-xs text-muted">
        <Term definition="Buy more units and the unit price drops to the next tier. A purchase order automatically picks the best tier your quantity qualifies for.">
          Tiered pricing
        </Term>{" "}
        is applied automatically when you reorder.
      </p>
    </div>
  );
}
