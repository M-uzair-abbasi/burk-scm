"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { CheckCircle2, ScanLine, TriangleAlert } from "lucide-react";

import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Panel } from "@/components/ui/Panel";
import { PageHeader } from "@/components/ui/PageHeader";
import { ChannelTag } from "@/components/ui/StatusPill";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/Table";
import { ApiError } from "@/lib/api";
import { packing } from "@/lib/resources";
import { formatDateTime, formatPKR } from "@/lib/format";
import type { PackQueueOrder } from "@/lib/types";

export default function PackingQueuePage() {
  const router = useRouter();
  const [rows, setRows] = useState<PackQueueOrder[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    packing
      .queue()
      .then((queue) => {
        if (alive) setRows(queue);
      })
      .catch(() => {})
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, []);

  async function startPacking(order: PackQueueOrder) {
    setError(null);
    setBusyId(order.id);
    try {
      const session = await packing.start(order.id);
      router.push(`/packing/${session.id}`);
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Could not start packing.",
      );
      setBusyId(null);
    }
  }

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        title="Packing station"
        description="Orders waiting to be packed, oldest first. Open one and scan every item before sealing — the station blocks anything that does not belong to that order, so a wrong item can never reach a customer."
      />

      {error ? (
        <div className="flex items-center gap-2 rounded-lg border border-critical/30 bg-critical-soft px-4 py-2.5 text-sm text-critical-text">
          <TriangleAlert aria-hidden className="size-4 shrink-0" />
          {error}
        </div>
      ) : null}

      <Panel
        eyebrow="Queue"
        title={
          loading
            ? "Loading…"
            : `${rows.length} order${rows.length === 1 ? "" : "s"} awaiting packing`
        }
        icon={ScanLine}
        bodyClassName="p-0"
      >
        {loading ? (
          <div className="px-5 py-12 text-center text-sm text-secondary">
            Loading the queue…
          </div>
        ) : rows.length === 0 ? (
          <div className="p-5">
            <EmptyState
              icon={CheckCircle2}
              title="Nothing is waiting to be packed"
              body="Every confirmed order has been packed and sealed. New orders land here automatically as soon as a channel sync brings them in."
              action={
                <Button variant="secondary" onClick={() => router.push("/orders")}>
                  View all orders
                </Button>
              }
            />
          </div>
        ) : (
          <Table>
            <THead>
              <TH>Ref</TH>
              <TH>Channel</TH>
              <TH>Order #</TH>
              <TH>Customer</TH>
              <TH align="right">Items</TH>
              <TH align="right">Total</TH>
              <TH>Placed</TH>
              <TH align="right">Action</TH>
            </THead>
            <TBody>
              {rows.map((o, index) => (
                <TR key={o.id}>
                  <TD mono className="font-semibold">
                    {o.reference}
                  </TD>
                  <TD>
                    <ChannelTag channel={o.channel} label={o.channel_display} />
                  </TD>
                  <TD mono className="text-secondary">
                    {o.external_id}
                  </TD>
                  <TD className="font-medium">{o.customer_name || "—"}</TD>
                  <TD align="right" mono>
                    {o.item_count}
                  </TD>
                  <TD align="right" mono>
                    {formatPKR(o.total)}
                  </TD>
                  <TD className="whitespace-nowrap text-xs text-secondary">
                    {formatDateTime(o.placed_at)}
                  </TD>
                  <TD align="right">
                    {/* Only the head of the queue gets the filled button: the
                        station is meant to be worked oldest-first, and two
                        equally loud buttons would make that ordering invisible. */}
                    <Button
                      size="sm"
                      variant={index === 0 ? "primary" : "secondary"}
                      disabled={busyId === o.id}
                      onClick={() => startPacking(o)}
                    >
                      {busyId === o.id ? "Opening…" : "Start packing"}
                    </Button>
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
        )}
      </Panel>
    </div>
  );
}
