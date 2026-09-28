"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { PackageSearch } from "lucide-react";

import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { SearchInput } from "@/components/ui/Input";
import { Meter } from "@/components/ui/Meter";
import { Panel } from "@/components/ui/Panel";
import { PageHeader } from "@/components/ui/PageHeader";
import { ALL, Select } from "@/components/ui/Select";
import { StatusPill } from "@/components/ui/StatusPill";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/Table";
import { Term } from "@/components/ui/Tooltip";
import { cn } from "@/components/ui/cn";
import { stockLabel, stockTone } from "@/components/ui/status";
import { categories as categoriesApi, products } from "@/lib/resources";
import type { Category, Product } from "@/lib/types";

function InventoryInner() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const [rows, setRows] = useState<Product[]>([]);
  const [cats, setCats] = useState<Category[]>([]);
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState(ALL);
  // Deep links from the dashboard ("4 low stock →") arrive as ?low=1, so the
  // filter has to start switched on or the link would appear to do nothing.
  const [lowOnly, setLowOnly] = useState(searchParams.get("low") === "1");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    categoriesApi
      .list()
      .then((r) => {
        if (alive) setCats(r.results);
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, []);

  // Debounce so typing in the search box doesn't fire a request per keystroke.
  useEffect(() => {
    const t = setTimeout(() => {
      setLoading(true);
      products
        .list({
          search,
          category: category === ALL ? undefined : category,
          low_stock: lowOnly || undefined,
        })
        .then((r) => setRows(r.results))
        .finally(() => setLoading(false));
    }, 250);
    return () => clearTimeout(t);
  }, [search, category, lowOnly]);

  const categoryOptions = [
    { value: ALL, label: "All categories" },
    ...cats.map((c) => ({ value: String(c.id), label: c.name })),
  ];
  const filtered = search.trim() !== "" || category !== ALL || lowOnly;

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        title="Inventory"
        description="Every product the warehouse tracks, with live stock against its safety level. Stock moves automatically as orders are packed and purchase orders received."
      />

      <Panel
        bodyClassName="p-0"
        eyebrow="Catalogue"
        title={
          loading
            ? "Loading…"
            : `${rows.length} product${rows.length === 1 ? "" : "s"}${filtered ? " matching" : ""}`
        }
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <SearchInput
              placeholder="SKU, name or barcode…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full sm:w-60"
            />
            <Select
              value={category}
              onValueChange={setCategory}
              options={categoryOptions}
              ariaLabel="Filter by category"
            />
            <label
              className={cn(
                "inline-flex h-9 cursor-pointer select-none items-center gap-2 rounded-md border px-3 text-sm transition-colors duration-150",
                lowOnly
                  ? "border-warning/50 bg-warning-soft text-warning-text"
                  : "border-strong bg-raised text-secondary hover:border-accent/50",
              )}
            >
              <input
                type="checkbox"
                checked={lowOnly}
                onChange={(e) => setLowOnly(e.target.checked)}
                className="size-3.5 accent-current"
              />
              Low stock only
            </label>
          </div>
        }
      >
        {loading ? (
          <div className="px-5 py-12 text-center text-sm text-secondary">
            Loading products…
          </div>
        ) : rows.length === 0 ? (
          <div className="p-5">
            <EmptyState
              icon={PackageSearch}
              title={
                filtered ? "No products match those filters" : "No products yet"
              }
              body={
                filtered
                  ? "Nothing in the catalogue matches what you have selected. Clearing the filters will show every product."
                  : "Products appear here once the catalogue is seeded. Each one carries its own barcode, which is what the packing station verifies against."
              }
              action={
                filtered ? (
                  <Button
                    variant="secondary"
                    onClick={() => {
                      setSearch("");
                      setCategory(ALL);
                      setLowOnly(false);
                    }}
                  >
                    Clear filters
                  </Button>
                ) : undefined
              }
            />
          </div>
        ) : (
          <Table>
            <THead>
              <TH>SKU</TH>
              <TH>Name</TH>
              <TH>Barcode</TH>
              <TH>Category</TH>
              <TH align="right">On hand</TH>
              <TH align="right">Safety</TH>
              <TH>Level</TH>
              <TH>Status</TH>
            </THead>
            <TBody>
              {rows.map((p) => {
                const tone = stockTone(p.quantity_on_hand, p.safety_stock);
                return (
                  <TR
                    key={p.id}
                    onClick={() => router.push(`/inventory/${p.id}`)}
                  >
                    <TD mono>{p.sku}</TD>
                    <TD className="font-medium">{p.name}</TD>
                    <TD mono className="text-secondary">
                      {p.barcode ?? "—"}
                    </TD>
                    <TD className="text-secondary">{p.category_name ?? "—"}</TD>
                    <TD align="right" mono className="font-semibold">
                      {p.quantity_on_hand}
                    </TD>
                    <TD align="right" mono className="text-secondary">
                      {p.safety_stock}
                    </TD>
                    <TD>
                      <div className="w-20">
                        <Meter
                          value={p.quantity_on_hand}
                          max={Math.max(p.safety_stock, 1)}
                          tone={tone}
                          label={`${p.name} stock level`}
                        />
                      </div>
                    </TD>
                    <TD>
                      <StatusPill
                        tone={tone}
                        variant={tone === "critical" ? "solid" : "soft"}
                      >
                        {stockLabel(p.quantity_on_hand, p.safety_stock)}
                      </StatusPill>
                    </TD>
                  </TR>
                );
              })}
            </TBody>
          </Table>
        )}
      </Panel>

      <p className="text-xs text-muted">
        <Term definition="The level you never want stock to fall under. Reaching it flags the product for reorder — it is a floor, not a target.">
          Safety stock
        </Term>{" "}
        is set per product. Open a product to adjust stock or raise a purchase
        order.
      </p>
    </div>
  );
}

export default function InventoryPage() {
  // useSearchParams needs a Suspense boundary for this statically-rendered route.
  return (
    <Suspense
      fallback={
        <div className="flex flex-col gap-5">
          <PageHeader
            title="Inventory"
            description="Every product the warehouse tracks, with live stock against its safety level."
          />
          <Panel bodyClassName="px-5 py-12">
            <p className="text-center text-sm text-secondary">Loading…</p>
          </Panel>
        </div>
      }
    >
      <InventoryInner />
    </Suspense>
  );
}
