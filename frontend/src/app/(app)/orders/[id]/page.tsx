"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  ArrowLeft,
  Bell,
  ChevronRight,
  Clock,
  Code2,
  Receipt,
  Truck,
  User,
} from "lucide-react";

import { useAuth } from "@/components/AuthProvider";
import { Button } from "@/components/ui/Button";
import { Panel } from "@/components/ui/Panel";
import { ChannelTag, LookPill, StatusPill } from "@/components/ui/StatusPill";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/Table";
import { Term } from "@/components/ui/Tooltip";
import { cn } from "@/components/ui/cn";
import {
  NOTIFICATION_STATUS,
  ORDER_STATUS,
  SHIPMENT_STATUS,
} from "@/components/ui/status";
import { ApiError } from "@/lib/api";
import { orders as ordersApi, shipments } from "@/lib/resources";
import { formatDateTime, formatPKR } from "@/lib/format";
import type { SalesOrder } from "@/lib/types";

function hasActiveAutomation(order: SalesOrder): boolean {
  const shipmentActive =
    !!order.shipment_job &&
    ["pending", "processing", "retry"].includes(order.shipment_job.status);
  const notificationActive = (order.notifications ?? []).some((notification) =>
    ["scheduled", "processing", "retrying", "accepted"].includes(
      notification.status,
    ),
  );
  return shipmentActive || notificationActive;
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="eyebrow text-muted">{label}</dt>
      <dd className="mt-1 text-sm text-primary">{value}</dd>
    </div>
  );
}

export default function OrderDetailPage() {
  const params = useParams<{ id: string }>();
  const { user } = useAuth();
  const id = Number(params.id);
  const [order, setOrder] = useState<SalesOrder | null>(null);
  const [loading, setLoading] = useState(true);
  const [showRaw, setShowRaw] = useState(false);
  const [shipBusy, setShipBusy] = useState(false);
  const [shipError, setShipError] = useState<string | null>(null);
  const [pollStopped, setPollStopped] = useState(false);
  const [pollCycle, setPollCycle] = useState(0);
  const pollAttempts = useRef(0);

  useEffect(() => {
    pollAttempts.current = 0;
    ordersApi
      .get(id)
      .then((loaded) => {
        setPollStopped(false);
        setOrder(loaded);
      })
      .finally(() => setLoading(false));
  }, [id]);

  const automationActive = order ? hasActiveAutomation(order) : false;
  useEffect(() => {
    if (!automationActive) return;
    let cancelled = false;

    async function poll() {
      while (!cancelled && pollAttempts.current < 30) {
        await new Promise((resolve) => window.setTimeout(resolve, 2_000));
        if (cancelled) return;
        try {
          const fresh = await ordersApi.get(id);
          if (cancelled) return;
          pollAttempts.current += 1;
          setOrder(fresh);
          if (!hasActiveAutomation(fresh)) return;
        } catch {
          setPollStopped(true);
          return;
        }
      }
      if (!cancelled) setPollStopped(true);
    }

    poll();
    return () => {
      cancelled = true;
    };
  }, [automationActive, id, pollCycle]);

  // Demo stand-in for a real courier webhook (Module 5); DELIVERED also
  // triggers Module 6's scheduled review reminder server-side.
  async function advanceShipment(status: "in_transit" | "delivered") {
    if (!order?.shipment) return;
    setShipBusy(true);
    setShipError(null);
    try {
      await shipments.advance(order.shipment.id, status);
      // Re-fetch rather than merge: DELIVERED also flips order.status and
      // creates a new (scheduled) review-request notification server-side.
      setOrder(await ordersApi.get(id));
    } catch (err) {
      setShipError(
        err instanceof ApiError ? err.message : "Could not advance shipment.",
      );
    } finally {
      setShipBusy(false);
    }
  }

  if (loading) {
    return <p className="py-12 text-center text-sm text-secondary">Loading…</p>;
  }
  if (!order) {
    return (
      <div className="py-12 text-center">
        <p className="text-sm text-secondary">That order could not be found.</p>
        <Link
          href="/orders"
          className="mt-3 inline-block text-sm text-accent-text hover:underline"
        >
          Back to orders
        </Link>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-5">
      <div>
        <Link
          href="/orders"
          className="inline-flex items-center gap-1.5 text-sm text-secondary transition-colors duration-150 hover:text-primary"
        >
          <ArrowLeft aria-hidden className="size-3.5" />
          Back to orders
        </Link>

        <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-2">
          <h1 className="tabular font-mono text-xl font-semibold tracking-tight text-primary">
            {order.reference}
          </h1>
          <ChannelTag channel={order.channel} label={order.channel_display} />
          <LookPill look={ORDER_STATUS[order.status]}>
            {order.status_display}
          </LookPill>
          <span className="tabular font-mono text-xs text-muted">
            {order.external_id}
          </span>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Panel eyebrow="Customer" title="Who it goes to" icon={User} bodyClassName="p-5">
          <dl className="flex flex-col gap-3">
            <Field label="Name" value={order.customer_name || "—"} />
            <Field label="Phone" value={order.customer_phone || "—"} />
            <Field label="Email" value={order.customer_email || "—"} />
            <Field label="Ship to" value={order.shipping_address || "—"} />
          </dl>
        </Panel>

        <Panel eyebrow="Timeline" title="When things happened" icon={Clock} bodyClassName="p-5">
          <dl className="flex flex-col gap-3">
            <Field
              label="Placed on channel"
              value={formatDateTime(order.placed_at)}
            />
            <Field
              label="First ingested"
              value={formatDateTime(order.ingested_at)}
            />
            <Field
              label="Last synced"
              value={formatDateTime(order.last_synced_at)}
            />
            <Field
              label="Channel-reported status"
              value={order.source_status_display}
            />
          </dl>
        </Panel>

        <Panel eyebrow="Money" title="Totals" icon={Receipt} bodyClassName="p-5">
          <dl className="flex flex-col gap-2 text-sm">
            <div className="flex justify-between">
              <dt className="text-secondary">Subtotal</dt>
              <dd className="tabular font-mono text-primary">
                {formatPKR(order.subtotal)}
              </dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-secondary">Shipping</dt>
              <dd className="tabular font-mono text-primary">
                {formatPKR(order.shipping_fee)}
              </dd>
            </div>
            <div className="mt-1 flex justify-between border-t border-subtle pt-2.5">
              <dt className="font-semibold text-primary">Total</dt>
              <dd className="tabular font-mono font-semibold text-primary">
                {formatPKR(order.total)}
              </dd>
            </div>
          </dl>
        </Panel>
      </div>

      <Panel eyebrow="Contents" title="Order lines" bodyClassName="p-0">
        <Table>
          <THead>
            <TH>SKU</TH>
            <TH>Product</TH>
            <TH align="right">Qty</TH>
            <TH align="right">Unit price</TH>
            <TH align="right">Line total</TH>
          </THead>
          <TBody>
            {(order.lines ?? []).map((l) => (
              <TR key={l.id}>
                <TD mono>{l.sku || "—"}</TD>
                <TD>
                  {l.product ? (
                    <Link
                      href={`/inventory/${l.product}`}
                      className="font-medium text-accent-text hover:underline"
                    >
                      {l.product_name}
                    </Link>
                  ) : (
                    <span className="flex flex-wrap items-center gap-2">
                      <span className="font-medium text-primary">
                        {l.product_name}
                      </span>
                      <Term definition="This SKU came from the channel but is not in our catalogue, so it has no stock record and cannot be barcode-verified.">
                        <StatusPill tone="warning" variant="soft">
                          unstocked SKU
                        </StatusPill>
                      </Term>
                    </span>
                  )}
                </TD>
                <TD align="right" mono>
                  {l.quantity}
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

      {order.shipment || order.shipment_job ? (
        <Panel
          eyebrow="Logistics"
          title="Shipment"
          icon={Truck}
          bodyClassName="p-5"
        >
          {order.shipment ? (
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex flex-wrap items-center gap-2.5">
                <span className="text-sm font-medium text-primary">
                  {order.shipment.courier_display}
                </span>
                <Term definition="The courier's tracking number for this parcel, also called an airway bill.">
                  <span className="tabular font-mono text-sm text-secondary">
                    {order.shipment.tracking_number}
                  </span>
                </Term>
                <LookPill look={SHIPMENT_STATUS[order.shipment.status]}>
                  {order.shipment.status_display}
                </LookPill>
              </div>
              {user?.is_manager ? (
                <div className="flex gap-2">
                  {order.shipment.status === "booked" ? (
                    <Button
                      size="sm"
                      variant="secondary"
                      disabled={shipBusy}
                      onClick={() => advanceShipment("in_transit")}
                    >
                      Simulate: in transit
                    </Button>
                  ) : null}
                  {order.shipment.status === "in_transit" ? (
                    <Button
                      size="sm"
                      variant="secondary"
                      disabled={shipBusy}
                      onClick={() => advanceShipment("delivered")}
                    >
                      Simulate: delivered
                    </Button>
                  ) : null}
                </div>
              ) : null}
            </div>
          ) : (
            <div className="flex flex-wrap items-center gap-2">
              <StatusPill
                tone={
                  order.shipment_job?.status === "failed"
                    ? "critical"
                    : "warning"
                }
                variant={
                  order.shipment_job?.status === "failed" ? "solid" : "outline"
                }
              >
                {order.shipment_job?.status === "retry"
                  ? "Retry scheduled"
                  : order.shipment_job?.status === "failed"
                    ? "Booking failed"
                    : order.shipment_job?.status === "processing"
                      ? "Booking courier…"
                      : "Queued"}
              </StatusPill>
              <span className="tabular text-xs text-secondary">
                attempt {order.shipment_job?.attempts ?? 0}/
                {order.shipment_job?.max_attempts ?? 0}
              </span>
              {user?.is_manager && order.shipment_job?.error ? (
                <p className="w-full text-xs text-critical-text">
                  {order.shipment_job.error}
                </p>
              ) : null}
            </div>
          )}

          {shipError ? (
            <p className="mt-3 text-sm text-critical-text">{shipError}</p>
          ) : null}

          {order.shipment ? (
            <ul className="mt-4 flex flex-col gap-1.5 border-t border-subtle pt-3">
              {order.shipment.events.map((e) => (
                <li
                  key={e.id}
                  className="flex items-center gap-2 text-xs text-secondary"
                >
                  <span className="tabular font-mono">
                    {formatDateTime(e.occurred_at)}
                  </span>
                  <ChevronRight aria-hidden className="size-3 text-muted" />
                  {e.status_display}
                </li>
              ))}
            </ul>
          ) : null}
        </Panel>
      ) : null}

      {pollStopped && hasActiveAutomation(order) ? (
        <Button
          variant="secondary"
          className="self-start"
          onClick={async () => {
            pollAttempts.current = 0;
            setPollStopped(false);
            setPollCycle((cycle) => cycle + 1);
            setOrder(await ordersApi.get(id));
          }}
        >
          Refresh automation status
        </Button>
      ) : null}

      {(order.notifications ?? []).length > 0 ? (
        <Panel
          eyebrow="Customer contact"
          title="Notifications sent"
          icon={Bell}
          bodyClassName="divide-y divide-subtle"
        >
          {(order.notifications ?? []).map((n) => (
            <div
              key={n.id}
              className="flex flex-wrap items-center justify-between gap-2 px-5 py-3 text-sm"
            >
              <div className="min-w-0">
                <span className="font-medium text-primary">
                  {n.kind_display}
                </span>
                <span className="ml-2 text-secondary">
                  via {n.channel_display} → {n.recipient || "—"}
                </span>
              </div>
              <div className="flex items-center gap-3">
                {n.status === "sent" ? (
                  <span className="tabular text-xs text-muted">
                    {n.latency_seconds !== null
                      ? `${n.latency_seconds.toFixed(1)}s latency`
                      : formatDateTime(n.sent_at)}
                  </span>
                ) : null}
                {n.status === "scheduled" && n.scheduled_for ? (
                  <span className="tabular text-xs text-muted">
                    due {formatDateTime(n.scheduled_for)}
                  </span>
                ) : null}
                <LookPill look={NOTIFICATION_STATUS[n.status]}>
                  {n.status_display}
                </LookPill>
              </div>
              {user?.is_manager && n.error ? (
                <p className="basis-full text-right text-xs text-critical-text">
                  {n.error}
                </p>
              ) : null}
            </div>
          ))}
        </Panel>
      ) : null}

      <Panel bodyClassName="p-4">
        <button
          onClick={() => setShowRaw((v) => !v)}
          className="flex items-center gap-1.5 text-sm font-medium text-secondary transition-colors duration-150 hover:text-primary"
        >
          <Code2 aria-hidden className="size-4" />
          <ChevronRight
            aria-hidden
            className={cn(
              "size-3.5 transition-transform duration-150",
              showRaw && "rotate-90",
            )}
          />
          Raw channel payload
        </button>
        {showRaw ? (
          <pre className="mt-3 overflow-x-auto rounded-lg bg-sunken p-3 text-xs text-secondary">
            {JSON.stringify(order.raw_payload ?? {}, null, 2)}
          </pre>
        ) : null}
      </Panel>
    </div>
  );
}
