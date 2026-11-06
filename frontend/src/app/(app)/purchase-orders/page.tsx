"use client";

import { useCallback, useEffect, useState } from "react";
import { ClipboardList, TriangleAlert } from "lucide-react";

import { useAuth } from "@/components/AuthProvider";
import { Button, ButtonLink } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Panel } from "@/components/ui/Panel";
import { PageHeader } from "@/components/ui/PageHeader";
import { LookPill } from "@/components/ui/StatusPill";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/Table";
import { Term } from "@/components/ui/Tooltip";
import { PO_STATUS } from "@/components/ui/status";
import { ApiError } from "@/lib/api";
import { purchaseOrders } from "@/lib/resources";
import { formatDate, formatPKR } from "@/lib/format";
import type { PurchaseOrder } from "@/lib/types";

export default function PurchaseOrdersPage() {
  const { user } = useAuth();
  const [pos, setPos] = useState<PurchaseOrder[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(() => {
    return purchaseOrders
      .list()
      .then((r) => setPos(r.results))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    let alive = true;
    purchaseOrders
      .list()
      .then((r) => {
        if (alive) setPos(r.results);
      })
      .catch(() => {})
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, []);

  async function act(id: number, fn: () => Promise<unknown>) {
    setError(null);
    setBusyId(id);
    try {
      await fn();
      await reload();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Action failed.");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        title="Purchase orders"
        description="Restock requests raised against your suppliers. Receiving one puts its stock back on the shelf automatically — you never adjust quantities by hand."
      />

      {error ? (
        <div className="flex items-center gap-2 rounded-lg border border-critical/30 bg-critical-soft px-4 py-2.5 text-sm text-critical-text">
          <TriangleAlert aria-hidden className="size-4 shrink-0" />
          {error}
        </div>
      ) : null}

      {loading ? (
        <Panel bodyClassName="px-5 py-12">
          <p className="text-center text-sm text-secondary">
            Loading purchase orders…
          </p>
        </Panel>
      ) : pos.length === 0 ? (
        /* The old version of this screen was a dead end: one grey sentence
           telling you to "reorder a low-stock product" with no way to get
           there. The route to the next step now ships with the message. */
        <Panel bodyClassName="p-5">
          <EmptyState
            icon={ClipboardList}
            title="No purchase orders yet"
            body="A purchase order is how you restock. Open any product that has fallen to its safety level and choose Reorder — the preferred supplier, lead time and tier pricing are filled in for you, and a draft appears here."
            action={
              <ButtonLink href="/inventory?low=1" variant="primary">
                Review low-stock items
              </ButtonLink>
            }
            hint="Receiving a purchase order returns its quantities to stock automatically."
          />
        </Panel>
      ) : (
        pos.map((po) => (
          <Panel
            key={po.id}
            bodyClassName="p-0"
            title={po.po_number}
            eyebrow={po.supplier_name}
            actions={
              <div className="flex items-center gap-3">
                <div className="text-right">
                  <div className="tabular text-sm font-semibold text-primary">
                    {formatPKR(po.total_amount)}
                  </div>
                  <div className="text-xs text-muted">
                    {po.expected_date
                      ? `expected ${formatDate(po.expected_date)}`
                      : `created ${formatDate(po.created_at)}`}
                  </div>
                </div>
                <LookPill look={PO_STATUS[po.status]}>
                  {po.status_display}
                </LookPill>
                {user?.is_manager && po.status === "draft" ? (
                  <Button
                    size="sm"
                    variant="primary"
                    disabled={busyId === po.id}
                    onClick={() => act(po.id, () => purchaseOrders.submit(po.id))}
                  >
                    {busyId === po.id ? "…" : "Submit"}
                  </Button>
                ) : null}
                {user?.is_manager &&
                (po.status === "submitted" ||
                  po.status === "partially_received") ? (
                  <Button
                    size="sm"
                    variant="primary"
                    disabled={busyId === po.id}
                    onClick={() =>
                      act(po.id, () => purchaseOrders.receive(po.id))
                    }
                  >
                    {busyId === po.id ? "…" : "Receive"}
                  </Button>
                ) : null}
              </div>
            }
          >
            <Table>
              <THead>
                <TH>Product</TH>
                <TH align="right">Ordered</TH>
                <TH align="right">Received</TH>
                <TH align="right">Unit price</TH>
                <TH align="right">Line total</TH>
              </THead>
              <TBody>
                {po.lines.map((l) => (
                  <TR key={l.id}>
                    <TD>
                      <span className="font-medium text-primary">
                        {l.product_name}
                      </span>
                      <span className="tabular ml-2 font-mono text-xs text-muted">
                        {l.product_sku}
                      </span>
                    </TD>
                    <TD align="right" mono>
                      {l.quantity_ordered}
                    </TD>
                    <TD align="right" mono>
                      {l.quantity_received}
                    </TD>
                    <TD align="right" mono>
                      {formatPKR(l.unit_price)}
                    </TD>
                    <TD align="right" mono className="font-medium">
                      {formatPKR(l.line_total)}
                    </TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          </Panel>
        ))
      )}

      {pos.length > 0 ? (
        <p className="text-xs text-muted">
          A{" "}
          <Term definition="A draft has not been sent to the supplier yet — you can still change it. Submitting locks it and starts the lead-time clock.">
            draft
          </Term>{" "}
          becomes live once submitted.{" "}
          <Term definition="Receiving records what physically arrived and writes those quantities back into stock as a movement, so the ledger always matches the shelf.">
            Receiving
          </Term>{" "}
          returns stock to the shelf.
        </p>
      ) : null}
    </div>
  );
}
