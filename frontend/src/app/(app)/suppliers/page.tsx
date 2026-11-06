"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Building2 } from "lucide-react";

import { Panel } from "@/components/ui/Panel";
import { PageHeader } from "@/components/ui/PageHeader";
import { EmptyState } from "@/components/ui/EmptyState";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/Table";
import { Term } from "@/components/ui/Tooltip";
import { suppliers as suppliersApi } from "@/lib/resources";
import type { Supplier } from "@/lib/types";

export default function SuppliersPage() {
  const router = useRouter();
  const [rows, setRows] = useState<Supplier[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    suppliersApi
      .list()
      .then((r) => {
        if (alive) setRows(r.results);
      })
      .catch(() => {})
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, []);

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        title="Suppliers"
        description="Who you restock from. Each supplier carries its own lead time and tiered pricing, which is what a purchase order uses to price itself."
      />

      <Panel bodyClassName="p-0">
        {loading ? (
          <div className="px-5 py-12 text-center text-sm text-secondary">
            Loading suppliers…
          </div>
        ) : rows.length === 0 ? (
          <div className="p-5">
            <EmptyState
              icon={Building2}
              title="No suppliers yet"
              body="Suppliers are the businesses you buy stock from. Once one is linked to a product, that product can be reordered in a couple of clicks."
            />
          </div>
        ) : (
          <Table>
            <THead>
              <TH>Code</TH>
              <TH>Name</TH>
              <TH>City</TH>
              <TH>Contact</TH>
              <TH align="right">Lead time</TH>
              <TH align="right">Products</TH>
            </THead>
            <TBody>
              {rows.map((s) => (
                <TR key={s.id} onClick={() => router.push(`/suppliers/${s.id}`)}>
                  <TD mono>{s.code}</TD>
                  <TD className="font-medium">{s.name}</TD>
                  <TD className="text-secondary">{s.city || "—"}</TD>
                  <TD className="text-secondary">{s.contact_person || "—"}</TD>
                  <TD align="right" mono>
                    {s.default_lead_time_days} days
                  </TD>
                  <TD align="right" mono>
                    {s.product_count}
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
        )}
      </Panel>

      <p className="text-xs text-muted">
        <Term definition="How many days the supplier typically takes to deliver after a purchase order is submitted. It sets the expected date on any PO raised against them.">
          Lead time
        </Term>{" "}
        can be overridden per product.
      </p>
    </div>
  );
}
