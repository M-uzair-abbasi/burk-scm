"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  ArrowLeft,
  BadgeCheck,
  Bell,
  Check,
  CircleAlert,
  ScanLine,
  Truck,
  Video,
  X,
} from "lucide-react";

import { useAuth } from "@/components/AuthProvider";
import { Button, ButtonLink } from "@/components/ui/Button";
import { Meter } from "@/components/ui/Meter";
import { Panel } from "@/components/ui/Panel";
import { ChannelTag, LookPill, StatusPill } from "@/components/ui/StatusPill";
import { Term } from "@/components/ui/Tooltip";
import { cn } from "@/components/ui/cn";
import {
  NOTIFICATION_STATUS,
  RECORDING_STATUS,
  SCAN_RESULT,
  SHIPMENT_STATUS,
} from "@/components/ui/status";
import { ApiError } from "@/lib/api";
import { packing } from "@/lib/resources";
import type { PackLine, PackSession, ScanResult } from "@/lib/types";

/** Self-contained Web Audio beep — no asset files. Harsh buzz on error, soft blip on ok. */
function beep(kind: "ok" | "error") {
  try {
    const Ctx =
      window.AudioContext ||
      (window as unknown as { webkitAudioContext: typeof AudioContext })
        .webkitAudioContext;
    const ctx = new Ctx();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain);
    gain.connect(ctx.destination);
    if (kind === "error") {
      osc.type = "square";
      osc.frequency.value = 150;
      gain.gain.value = 0.18;
      osc.start();
      osc.stop(ctx.currentTime + 0.45);
    } else {
      osc.type = "sine";
      osc.frequency.value = 880;
      gain.gain.value = 0.06;
      osc.start();
      osc.stop(ctx.currentTime + 0.08);
    }
    osc.onended = () => ctx.close();
  } catch {
    // Audio unavailable — the visual flash still fires.
  }
}

/** Instant client verdict so the flash/beep fires without waiting on the server. */
function clientCheck(lines: PackLine[], barcode: string): ScanResult {
  const line = lines.find((l) => l.barcode && l.barcode === barcode);
  if (!line) return "mismatch";
  if (line.scanned >= line.required) return "overscan";
  return "ok";
}

function hasActiveAutomation(session: PackSession): boolean {
  const recordingActive =
    !!session.recording &&
    ["pending", "recording", "queued", "processing", "retrying"].includes(
      session.recording.status,
    );
  const shipmentActive =
    !!session.shipment_job &&
    ["pending", "processing", "retry"].includes(session.shipment_job.status);
  const notificationActive = session.video_notifications.some((notification) =>
    ["scheduled", "processing", "retrying", "accepted"].includes(
      notification.status,
    ),
  );
  return (
    session.status === "completed" &&
    (recordingActive || shipmentActive || notificationActive)
  );
}

/** One row of the post-seal automation chain. */
function AutomationStep({
  icon: Icon,
  title,
  blurb,
  children,
}: {
  icon: typeof Video;
  title: string;
  blurb: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex gap-3.5 px-5 py-4">
      <span className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-full bg-sunken text-muted">
        <Icon aria-hidden className="size-4" />
      </span>
      <div className="min-w-0 flex-1">
        <div className="text-sm font-semibold text-primary">{title}</div>
        <p className="mt-0.5 text-xs leading-relaxed text-secondary">{blurb}</p>
        <div className="mt-2.5">{children}</div>
      </div>
    </div>
  );
}

export default function PackingStationPage() {
  const { user } = useAuth();
  const params = useParams<{ id: string }>();
  const id = Number(params.id);
  const inputRef = useRef<HTMLInputElement>(null);

  const [session, setSession] = useState<PackSession | null>(null);
  const [loading, setLoading] = useState(true);
  const [input, setInput] = useState("");
  const [flash, setFlash] = useState<null | "error">(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pollStopped, setPollStopped] = useState(false);
  const [pollCycle, setPollCycle] = useState(0);
  const pollAttempts = useRef(0);

  useEffect(() => {
    pollAttempts.current = 0;
    packing
      .get(id)
      .then((loaded) => {
        setPollStopped(false);
        setSession(loaded);
      })
      .finally(() => setLoading(false));
  }, [id]);

  const automationActive = session ? hasActiveAutomation(session) : false;
  useEffect(() => {
    if (!automationActive) return;
    let cancelled = false;

    async function poll() {
      while (!cancelled && pollAttempts.current < 30) {
        await new Promise((resolve) => window.setTimeout(resolve, 2_000));
        if (cancelled) return;
        try {
          const fresh = await packing.get(id);
          if (cancelled) return;
          pollAttempts.current += 1;
          setSession(fresh);
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

  const focusInput = useCallback(() => inputRef.current?.focus(), []);
  useEffect(() => {
    focusInput();
  }, [focusInput, session]);

  function flashError() {
    beep("error");
    setFlash("error");
    setTimeout(() => setFlash(null), 550);
  }

  const submitScan = useCallback(
    async (raw: string) => {
      const code = raw.trim();
      setInput("");
      if (!code || !session || session.status !== "in_progress") return;

      // Instant client verdict for real-time flash/beep (hybrid design).
      if (clientCheck(session.lines, code) === "ok") beep("ok");
      else flashError();

      try {
        const res = await packing.scan(session.id, code);
        setSession(res.session); // authoritative counts + history
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Scan failed.");
      }
      focusInput();
    },
    [session, focusInput],
  );

  async function confirmLine(lineId: number) {
    if (!session) return;
    try {
      setSession(await packing.confirmLine(session.id, lineId));
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Could not confirm line.",
      );
    }
    focusInput();
  }

  async function onComplete() {
    if (!session) return;
    setBusy(true);
    setError(null);
    pollAttempts.current = 0;
    setPollStopped(false);
    try {
      // Completion commits stock plus durable recording/shipment jobs. External
      // work proceeds in the worker and the bounded poll reflects that state.
      setSession(await packing.complete(session.id));
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Could not complete pack.",
      );
    } finally {
      setBusy(false);
    }
  }

  function simulateCorrect() {
    if (!session) return;
    const next = session.lines.find(
      (l) => l.has_barcode && l.scanned < l.required,
    );
    if (next?.barcode) submitScan(next.barcode);
  }

  if (loading) {
    return (
      <p className="py-12 text-center text-sm text-secondary">
        Opening the station…
      </p>
    );
  }
  if (!session) {
    return (
      <div className="py-12 text-center">
        <p className="text-sm text-secondary">
          That packing session could not be found.
        </p>
        <ButtonLink href="/packing" variant="secondary" className="mt-4">
          Back to the queue
        </ButtonLink>
      </div>
    );
  }

  const done = session.status === "completed";
  const totalRequired = session.lines.reduce((a, l) => a + l.required, 0);
  const totalScanned = session.lines.reduce(
    (a, l) => a + Math.min(l.scanned, l.required),
    0,
  );

  return (
    <div className="relative flex flex-col gap-5">
      {/* Full-screen mismatch flash — deliberately impossible to miss. */}
      {flash === "error" ? (
        <div className="pointer-events-none fixed inset-0 z-50 flex items-center justify-center bg-critical/90">
          <div className="text-center text-white">
            <X aria-hidden className="mx-auto size-20" strokeWidth={3} />
            <div className="mt-2 text-5xl font-black tracking-tight">
              WRONG ITEM
            </div>
            <div className="mt-3 text-lg">
              This item is not on this order — do not pack it.
            </div>
          </div>
        </div>
      ) : null}

      <div>
        <Link
          href="/packing"
          className="inline-flex items-center gap-1.5 text-sm text-secondary transition-colors duration-150 hover:text-primary"
        >
          <ArrowLeft aria-hidden className="size-3.5" />
          Back to queue
        </Link>

        <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-2">
          <h1 className="tabular font-mono text-xl font-semibold tracking-tight text-primary">
            {session.order.reference}
          </h1>
          <ChannelTag
            channel={session.order.channel}
            label={session.order.channel_display}
          />
          <span className="text-sm text-secondary">
            {session.order.customer_name || "—"}
          </span>
          <span className="tabular font-mono text-xs text-muted">
            {session.order.external_id}
          </span>
        </div>
      </div>

      {done ? (
        <>
          <section className="overflow-hidden rounded-xl border border-success/40 bg-raised shadow-card">
            <div className="flex flex-col items-center px-5 py-8 text-center">
              <span className="flex size-12 items-center justify-center rounded-full bg-success text-white">
                <Check aria-hidden className="size-6" strokeWidth={3} />
              </span>
              <h2 className="mt-3 text-lg font-semibold text-primary">
                Packed and sealed
              </h2>
              <p className="mt-1 max-w-md text-sm leading-relaxed text-secondary">
                Every item was barcode-verified. Stock has been decremented and
                the order marked Packed. Everything below now runs on its own.
              </p>
            </div>
          </section>

          <Panel
            eyebrow="Runs automatically after sealing"
            title="What the system is doing for this parcel"
            icon={BadgeCheck}
            bodyClassName="divide-y divide-subtle"
          >
            <AutomationStep
              icon={Video}
              title="Packaging video"
              blurb="Proof of what went into the box, filmed and compressed for the customer."
            >
              {!session.recording ? (
                <p className="text-sm text-secondary">
                  Recording state unavailable.
                </p>
              ) : session.recording.status === "ready" ? (
                <div className="space-y-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <LookPill look={RECORDING_STATUS.ready}>
                      Video ready
                    </LookPill>
                    <span className="tabular font-mono text-xs text-secondary">
                      {session.recording.duration_seconds?.toFixed(0)}s ·{" "}
                      {session.recording.compressed_size_bytes
                        ? `${Math.round(session.recording.compressed_size_bytes / 1024)} KB`
                        : "—"}
                    </span>
                  </div>
                  {session.recording.video_url ? (
                    <video
                      controls
                      className="w-full max-w-xs rounded-lg border border-subtle"
                      src={session.recording.video_url}
                    />
                  ) : null}
                </div>
              ) : (
                <div className="flex flex-wrap items-center gap-2">
                  <LookPill look={RECORDING_STATUS[session.recording.status]}>
                    {session.recording.status_display}
                  </LookPill>
                  <span className="text-xs text-secondary">
                    attempt {session.recording.processing_attempts}
                  </span>
                  {user?.is_manager && session.recording.error ? (
                    <p className="w-full text-xs text-critical-text">
                      {session.recording.error}
                    </p>
                  ) : null}
                </div>
              )}
            </AutomationStep>

            {session.video_notifications.length > 0 ? (
              <AutomationStep
                icon={Bell}
                title="Customer notified"
                blurb="The video link goes out over WhatsApp and email within seconds of sealing."
              >
                <ul className="flex flex-col gap-1.5">
                  {session.video_notifications.map((n) => (
                    <li
                      key={n.id}
                      className="flex flex-wrap items-center justify-between gap-2 text-sm"
                    >
                      <span className="text-secondary">
                        {n.channel_display} → {n.recipient || "—"}
                      </span>
                      <LookPill look={NOTIFICATION_STATUS[n.status]}>
                        {n.status === "sent" && n.latency_seconds !== null
                          ? `Sent in ${n.latency_seconds.toFixed(1)}s`
                          : n.status_display}
                      </LookPill>
                      {user?.is_manager && n.error ? (
                        <span className="w-full text-xs text-critical-text">
                          {n.error}
                        </span>
                      ) : null}
                    </li>
                  ))}
                </ul>
              </AutomationStep>
            ) : null}

            {session.shipment || session.shipment_job ? (
              <AutomationStep
                icon={Truck}
                title="Courier booked"
                blurb="A durable job books the courier and returns an airway bill — no manual entry."
              >
                {session.shipment ? (
                  <div className="flex flex-wrap items-center gap-2">
                    <LookPill look={SHIPMENT_STATUS[session.shipment.status]}>
                      {session.shipment.status_display}
                    </LookPill>
                    <span className="text-sm font-medium text-primary">
                      {session.shipment.courier_display}
                    </span>
                    <Term definition="The courier's tracking number for this parcel, also called an airway bill.">
                      <span className="tabular font-mono text-xs text-secondary">
                        {session.shipment.tracking_number}
                      </span>
                    </Term>
                  </div>
                ) : (
                  <div className="flex flex-wrap items-center gap-2">
                    <StatusPill
                      tone={
                        session.shipment_job?.status === "failed"
                          ? "critical"
                          : "warning"
                      }
                      variant={
                        session.shipment_job?.status === "failed"
                          ? "solid"
                          : "outline"
                      }
                    >
                      {session.shipment_job?.status === "retry"
                        ? "Retry scheduled"
                        : session.shipment_job?.status === "failed"
                          ? "Booking failed"
                          : session.shipment_job?.status === "processing"
                            ? "Booking courier…"
                            : "Queued"}
                    </StatusPill>
                    {user?.is_manager && session.shipment_job?.error ? (
                      <p className="w-full text-xs text-critical-text">
                        {session.shipment_job.error}
                      </p>
                    ) : null}
                  </div>
                )}
              </AutomationStep>
            ) : null}
          </Panel>

          <div className="flex flex-wrap items-center gap-3">
            <ButtonLink href="/packing" variant="primary">
              Back to queue
            </ButtonLink>
            {pollStopped && hasActiveAutomation(session) ? (
              <Button
                variant="secondary"
                onClick={async () => {
                  pollAttempts.current = 0;
                  setPollStopped(false);
                  setPollCycle((cycle) => cycle + 1);
                  setSession(await packing.get(session.id));
                }}
              >
                Refresh automation status
              </Button>
            ) : null}
          </div>
        </>
      ) : (
        <>
          <Panel
            eyebrow="Step 1 of 2"
            title="Scan every item in the parcel"
            icon={ScanLine}
            bodyClassName="p-4"
          >
            <form
              onSubmit={(e) => {
                e.preventDefault();
                submitScan(input);
              }}
            >
              <label
                htmlFor="barcode"
                className="eyebrow mb-1.5 block text-muted"
              >
                Scan item barcode
              </label>
              <input
                id="barcode"
                ref={inputRef}
                autoFocus
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="Scan or type a barcode, then press Enter…"
                className="tabular w-full rounded-lg border border-strong bg-raised px-4 py-3 font-mono text-lg text-primary outline-none transition-colors duration-150 placeholder:font-sans placeholder:text-base placeholder:text-muted hover:border-accent/50"
              />
            </form>

            <div className="mt-3 flex flex-wrap items-center gap-2">
              <span className="text-xs text-muted">Demo aids:</span>
              <Button size="sm" variant="secondary" onClick={simulateCorrect}>
                Simulate correct scan
              </Button>
              <Button
                size="sm"
                variant="secondary"
                onClick={() => submitScan("0000000000000")}
                className="border-critical/40 text-critical-text hover:bg-critical-soft"
              >
                Simulate wrong item
              </Button>
            </div>
          </Panel>

          {error ? (
            <div className="flex items-center gap-2 rounded-lg border border-critical/30 bg-critical-soft px-4 py-2.5 text-sm text-critical-text">
              <CircleAlert aria-hidden className="size-4 shrink-0" />
              {error}
            </div>
          ) : null}

          <Panel
            eyebrow="Packing list"
            title={`${totalScanned} of ${totalRequired} items verified`}
            actions={
              <div className="w-32">
                <Meter
                  value={totalScanned}
                  max={Math.max(totalRequired, 1)}
                  tone={session.complete ? "success" : "warning"}
                  label="Items verified"
                />
              </div>
            }
            bodyClassName="divide-y divide-subtle"
          >
            {session.lines.map((l) => (
              <div
                key={l.line_id}
                className={cn(
                  "flex items-center justify-between gap-3 px-5 py-3",
                  l.complete && "bg-success-soft/40",
                )}
              >
                <div className="flex min-w-0 items-center gap-3">
                  <span
                    className={cn(
                      "flex size-6 shrink-0 items-center justify-center rounded-full",
                      l.complete
                        ? "bg-success text-white"
                        : "border border-strong text-transparent",
                    )}
                  >
                    <Check aria-hidden className="size-3.5" strokeWidth={3} />
                  </span>
                  <div className="min-w-0">
                    <div className="truncate text-sm font-medium text-primary">
                      {l.product_name}
                    </div>
                    <div className="tabular font-mono text-xs text-muted">
                      {l.sku}
                      {l.barcode ? ` · ${l.barcode}` : " · no barcode"}
                    </div>
                  </div>
                </div>
                <div className="flex shrink-0 items-center gap-3">
                  <span className="tabular font-mono text-sm font-semibold text-primary">
                    {l.scanned}/{l.required}
                  </span>
                  {!l.has_barcode && !l.complete ? (
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={() => confirmLine(l.line_id)}
                    >
                      Confirm manually
                    </Button>
                  ) : null}
                </div>
              </div>
            ))}
          </Panel>

          <Panel
            eyebrow="Step 2 of 2"
            title="Seal the parcel"
            bodyClassName="flex flex-wrap items-center justify-between gap-3 p-5"
          >
            <p className="text-sm text-secondary">
              {session.complete
                ? "All items verified — you can seal and complete this pack."
                : "Completion unlocks once every item on the list has been scanned."}
            </p>
            <Button
              disabled={!session.complete || busy}
              onClick={onComplete}
              variant="primary"
              size="lg"
            >
              {busy ? "Completing…" : "Complete pack"}
            </Button>
          </Panel>

          {session.recent_scans.length > 0 ? (
            <Panel eyebrow="Audit trail" title="Recent scans" bodyClassName="p-4">
              <div className="flex flex-wrap gap-1.5">
                {session.recent_scans.map((s) => (
                  <LookPill
                    key={s.id}
                    look={SCAN_RESULT[s.result]}
                    className="tabular font-mono"
                  >
                    {s.manual ? "(manual)" : s.barcode || "—"} · {s.result}
                  </LookPill>
                ))}
              </div>
            </Panel>
          ) : null}
        </>
      )}
    </div>
  );
}
