"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  CheckCircle2,
  Inbox,
  RefreshCw,
  ShieldCheck,
  TriangleAlert,
} from "lucide-react";

import { useAuth } from "@/components/AuthProvider";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { SearchInput } from "@/components/ui/Input";
import { InstrumentPanel, Panel } from "@/components/ui/Panel";
import { PageHeader } from "@/components/ui/PageHeader";
import { ALL, Select } from "@/components/ui/Select";
import { ChannelTag, LookPill } from "@/components/ui/StatusPill";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/Table";
import { Term } from "@/components/ui/Tooltip";
import { cn } from "@/components/ui/cn";
import { ORDER_STATUS } from "@/components/ui/status";
import { ApiError } from "@/lib/api";
import { orders as ordersApi } from "@/lib/resources";
import { formatDateTime, formatPKR } from "@/lib/format";
import type { OrderSummary, SalesOrder } from "@/lib/types";

const STATUS_OPTIONS = [
  { value: ALL, label: "All statuses" },
  { value: "pending", label: "Pending" },
  { value: "confirmed", label: "Confirmed" },
  { value: "packed", label: "Packed" },
  { value: "shipped", label: "Shipped" },
  { value: "delivered", label: "Delivered" },
  { value: "cancelled", label: "Cancelled" },
  { value: "returned", label: "Returned" },
];

const CHANNEL_OPTIONS = [
  { value: ALL, label: "All channels" },
  { value: "burk", label: "Burk.pk" },
  { value: "daraz", label: "Daraz.pk" },
];

export default function OrdersPage() {
  const router = useRouter();
  const { user } = useAuth();
  const [rows, setRows] = useState<SalesOrder[]>([]);
  const [summary, setSummary] = useState<OrderSummary | null>(null);
  const [channel, setChannel] = useState(ALL);
  const [status, setStatus] = useState(ALL);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadList = useCallback(() => {
    return ordersApi
      .list({
        channel: channel === ALL ? undefined : channel,
        status: status === ALL ? undefined : status,
        search,
      })
      .then((r) => setRows(r.results));
  }, [channel, status, search]);

  useEffect(() => {
    let alive = true;
    ordersApi
      .summary()
      .then((s) => {
        if (alive) setSummary(s);
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
      loadList().finally(() => setLoading(false));
    }, 250);
    return () => clearTimeout(t);
  }, [loadList]);

  async function onSync() {
    setError(null);
    setSyncing(true);
    try {
      const res = await ordersApi.sync();
      const created = res.runs.reduce((a, r) => a + r.created, 0);
      const updated = res.runs.reduce((a, r) => a + r.updated, 0);
      const dup = res.runs.reduce((a, r) => a + r.duplicates_skipped, 0);
      const failed = res.runs.reduce((a, r) => a + r.failed, 0);
      if (res.overall_ok) {
        setToast(
          `Synced: ${created} new, ${updated} updated, ${dup} duplicate(s) skipped.`,
        );
      } else {
        const failedChannels = res.runs
          .filter((run) => !run.ok)
          .map((run) => run.channel_display)
          .join(", ");
        setToast(null);
        setError(
          `Sync incomplete: ${failed} record(s) failed. Check ${failedChannels || "channel errors"}.`,
        );
      }
      setSummary(res.summary);
      await loadList();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Sync failed.");
    } finally {
      setSyncing(false);
      setTimeout(() => setToast(null), 6000);
    }
  }

  const integrity = summary?.integrity;
  const filtered = channel !== ALL || status !== ALL || search.trim() !== "";

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        title="Orders"
        description="Every order pulled from your sales channels, reconciled so nothing is dropped, duplicated or silently changed at the source."
        actions={
          user?.is_manager ? (
            <Button onClick={onSync} disabled={syncing} variant="primary">
              <RefreshCw
                aria-hidden
                className={cn("size-4", syncing && "animate-spin")}
              />
              {syncing ? "Syncing…" : "Sync now"}
            </Button>
          ) : null
        }
      />

      {/* Reconciliation — this is the evidence that the queue is trustworthy,
          so it gets the instrument treatment rather than a grey chip. */}
      {integrity ? (
        <InstrumentPanel
          eyebrow="Channel reconciliation"
          title="Is anything missing from the queue?"
          status={
            <span
              className={cn(
                "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium",
                integrity.ok
                  ? "bg-success/15 text-success"
                  : "bg-critical/15 text-critical",
              )}
            >
              {integrity.ok ? (
                <ShieldCheck aria-hidden className="size-3.5" />
              ) : (
                <TriangleAlert aria-hidden className="size-3.5" />
              )}
              {integrity.ok ? "Fully reconciled" : "Discrepancy found"}
            </span>
          }
        >
          <div className="grid grid-cols-2 divide-x divide-y divide-instrument-border sm:grid-cols-3 lg:grid-cols-5 lg:divide-y-0">
            {[
              { label: "Dropped", value: integrity.dropped },
              { label: "Stale", value: integrity.stale },
              { label: "Duplicated", value: integrity.duplicated },
              { label: "Mismatched", value: integrity.mismatched },
              { label: "Unique orders", value: integrity.unique, good: true },
            ].map((cell) => (
              <div key={cell.label} className="p-4">
                <div className="eyebrow text-instrument-muted">
                  {cell.label}
                </div>
                <div
                  className={cn(
                    "tabular mt-2 font-mono text-lg font-semibold leading-none",
                    !cell.good && cell.value > 0
                      ? "text-critical"
                      : "text-instrument-text",
                  )}
                >
                  {cell.value}
                </div>
              </div>
            ))}
          </div>

          {summary ? (
            <div className="flex flex-wrap gap-x-6 gap-y-2 border-t border-instrument-border px-5 py-3">
              {Object.entries(summary.by_channel).map(([key, c]) => (
                <div key={key} className="text-xs">
                  <span className="font-medium text-instrument-text">
                    {c.label}
                  </span>
                  <span className="tabular font-mono text-instrument-text">
                    {" "}
                    · {c.count}
                  </span>
                  <span className="text-instrument-muted">
                    {" "}
                    · last sync {formatDateTime(c.last_sync)}
                  </span>
                </div>
              ))}
            </div>
          ) : null}
        </InstrumentPanel>
      ) : null}

      {toast ? (
        <div className="flex items-center gap-2 rounded-lg border border-success/30 bg-success-soft px-4 py-2.5 text-sm text-success-text">
          <CheckCircle2 aria-hidden className="size-4 shrink-0" />
          {toast}
        </div>
      ) : null}
      {error ? (
        <div className="flex items-center gap-2 rounded-lg border border-critical/30 bg-critical-soft px-4 py-2.5 text-sm text-critical-text">
          <TriangleAlert aria-hidden className="size-4 shrink-0" />
          {error}
        </div>
      ) : null}

      <Panel
        bodyClassName="p-0"
        eyebrow="Queue"
        title={
          loading
            ? "Loading…"
            : `${rows.length} order${rows.length === 1 ? "" : "s"}${filtered ? " matching" : ""}`
        }
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <SearchInput
              placeholder="Reference, order ID or customer…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full sm:w-64"
            />
            <Select
              value={channel}
              onValueChange={setChannel}
              options={CHANNEL_OPTIONS}
              ariaLabel="Filter by channel"
            />
            <Select
              value={status}
              onValueChange={setStatus}
              options={STATUS_OPTIONS}
              ariaLabel="Filter by status"
            />
          </div>
        }
      >
        {loading ? (
          <div className="px-5 py-12 text-center text-sm text-secondary">
            Loading orders…
          </div>
        ) : rows.length === 0 ? (
          <div className="p-5">
            <EmptyState
              icon={Inbox}
              title={filtered ? "No orders match those filters" : "No orders yet"}
              body={
                filtered
                  ? "Nothing in the queue matches what you have selected. Clearing the filters will show every order."
                  : "Orders appear here automatically once a channel feed has been pulled. You can trigger a pull yourself at any time."
              }
              action={
                filtered ? (
                  <Button
                    variant="secondary"
                    onClick={() => {
                      setChannel(ALL);
                      setStatus(ALL);
                      setSearch("");
                    }}
                  >
                    Clear filters
                  </Button>
                ) : user?.is_manager ? (
                  <Button variant="primary" onClick={onSync} disabled={syncing}>
                    <RefreshCw
                      aria-hidden
                      className={cn("size-4", syncing && "animate-spin")}
                    />
                    {syncing ? "Syncing…" : "Sync channels now"}
                  </Button>
                ) : undefined
              }
              hint={
                !filtered && !user?.is_manager
                  ? "Only a manager can trigger a channel sync."
                  : undefined
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
              <TH>Status</TH>
              <TH>Placed</TH>
            </THead>
            <TBody>
              {rows.map((o) => (
                <TR key={o.id} onClick={() => router.push(`/orders/${o.id}`)}>
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
                  <TD align="right" mono className="font-medium">
                    {formatPKR(o.total)}
                  </TD>
                  <TD>
                    <LookPill look={ORDER_STATUS[o.status]}>
                      {o.status_display}
                    </LookPill>
                  </TD>
                  <TD className="whitespace-nowrap text-xs text-secondary">
                    {formatDateTime(o.placed_at)}
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
        )}
      </Panel>

      <p className="text-xs text-muted">
        <Term definition="A source is 'stale' when the channel's own copy of an order is newer than ours — it means a sync is overdue, not that data was lost.">
          Stale
        </Term>{" "}
        and{" "}
        <Term definition="A 'dropped' order exists at the channel but never reached our queue. This count must stay at zero.">
          dropped
        </Term>{" "}
        counts are checked on every sync.
      </p>
    </div>
  );
}
