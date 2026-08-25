"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";

import { ChannelBadge } from "@/components/ChannelBadge";
import { useAuth } from "@/components/AuthProvider";
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
      setError(err instanceof ApiError ? err.message : "Could not confirm line.");
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
      setError(err instanceof ApiError ? err.message : "Could not complete pack.");
    } finally {
      setBusy(false);
    }
  }

  function simulateCorrect() {
    if (!session) return;
    const next = session.lines.find((l) => l.has_barcode && l.scanned < l.required);
    if (next?.barcode) submitScan(next.barcode);
  }

  if (loading) return <p className="text-sm text-zinc-500">Loading…</p>;
  if (!session) return <p className="text-sm text-zinc-500">Session not found.</p>;

  const done = session.status === "completed";

  return (
    <div className="relative space-y-5">
      {/* Full-screen mismatch flash */}
      {flash === "error" && (
        <div className="pointer-events-none fixed inset-0 z-50 flex items-center justify-center bg-red-600/85">
          <div className="text-center text-white">
            <div className="text-6xl font-black tracking-tight">✕ WRONG ITEM</div>
            <div className="mt-3 text-xl">
              This item is not on this order — do not pack it.
            </div>
          </div>
        </div>
      )}

      <Link
        href="/packing"
        className="inline-block text-sm text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100"
      >
        ← Back to queue
      </Link>

      <div className="flex flex-wrap items-center gap-3">
        <h2 className="font-mono text-lg font-semibold">{session.order.reference}</h2>
        <ChannelBadge
          channel={session.order.channel}
          label={session.order.channel_display}
        />
        <span className="text-sm text-zinc-500">
          {session.order.customer_name || "—"} · {session.order.external_id}
        </span>
      </div>

      {done ? (
        <div className="space-y-4">
          <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-5 py-8 text-center dark:border-emerald-900 dark:bg-emerald-950">
            <div className="text-2xl font-bold text-emerald-700 dark:text-emerald-300">
              ✓ Packed
            </div>
            <p className="mt-1 text-sm text-emerald-700/80 dark:text-emerald-300/80">
              Every item verified. Stock decremented and the order marked Packed.
            </p>
          </div>

          {/* Module 4: packaging video + customer dispatch */}
          <div className="rounded-xl border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-900">
            <h3 className="mb-3 text-xs font-semibold uppercase tracking-wide text-zinc-500">
              Customer transparency — packaging video
            </h3>

            {!session.recording ? (
              <p className="text-sm text-zinc-500">Recording state unavailable.</p>
            ) : session.recording.status === "failed" ? (
              <p className="text-sm text-red-600 dark:text-red-400">
                Recording failed
                {user?.is_manager && session.recording.error
                  ? `: ${session.recording.error}`
                  : ". Ask a manager to review the worker failure."}
              </p>
            ) : session.recording.status === "ready" ? (
              <div className="space-y-3">
                <div className="flex flex-wrap items-center gap-2 text-sm">
                  <span className="rounded-full bg-emerald-100 px-2 py-0.5 font-medium text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300">
                    ✓ Video ready
                  </span>
                  <span className="text-zinc-500">
                    {session.recording.duration_seconds?.toFixed(0)}s ·{" "}
                    {session.recording.compressed_size_bytes
                      ? `${Math.round(session.recording.compressed_size_bytes / 1024)} KB`
                      : "—"}
                  </span>
                </div>
                {session.recording.video_url && (
                  <video
                    controls
                    className="w-full max-w-xs rounded-lg border border-zinc-200 dark:border-zinc-800"
                    src={session.recording.video_url}
                  />
                )}
              </div>
            ) : (
              <div className="text-sm">
                <span className="font-medium text-amber-700 dark:text-amber-300">
                  {session.recording.status_display}
                </span>
                <span className="ml-2 text-zinc-500">
                  attempt {session.recording.processing_attempts}
                </span>
                {user?.is_manager && session.recording.error && (
                  <p className="mt-2 text-xs text-red-600 dark:text-red-400">
                    {session.recording.error}
                  </p>
                )}
              </div>
            )}

            {session.video_notifications.length > 0 && (
              <div className="mt-4 space-y-1.5 border-t border-zinc-100 pt-3 dark:border-zinc-800">
                {session.video_notifications.map((n) => (
                  <div key={n.id} className="flex items-center justify-between text-sm">
                    <span className="text-zinc-600 dark:text-zinc-300">
                      {n.channel_display} → {n.recipient || "—"}
                    </span>
                    <span
                      className={
                        n.status === "sent"
                          ? "font-medium text-emerald-600 dark:text-emerald-400"
                          : n.status === "failed"
                            ? "font-medium text-red-600 dark:text-red-400"
                            : "font-medium text-amber-600 dark:text-amber-400"
                      }
                    >
                      {n.status === "sent" && n.latency_seconds !== null
                        ? `Sent in ${n.latency_seconds.toFixed(1)}s`
                        : n.status_display}
                    </span>
                    {user?.is_manager && n.error && (
                      <span className="ml-2 text-xs text-red-600 dark:text-red-400">
                        {n.error}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Module 5: durable courier booking, right alongside the video panel */}
          {(session.shipment || session.shipment_job) && (
            <div className="rounded-xl border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-900">
              <h3 className="mb-3 text-xs font-semibold uppercase tracking-wide text-zinc-500">
                Shipment
              </h3>
              {session.shipment ? (
                <div className="flex flex-wrap items-center gap-2 text-sm">
                  <span className="rounded-full bg-emerald-100 px-2 py-0.5 font-medium text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300">
                    ✓ {session.shipment.status_display}
                  </span>
                  <span className="font-medium">
                    {session.shipment.courier_display}
                  </span>
                  <span className="font-mono text-zinc-500">
                    {session.shipment.tracking_number}
                  </span>
                </div>
              ) : (
                <div className="text-sm">
                  <span
                    className={
                      session.shipment_job?.status === "failed"
                        ? "font-medium text-red-600 dark:text-red-400"
                        : "font-medium text-amber-700 dark:text-amber-300"
                    }
                  >
                    {session.shipment_job?.status === "retry"
                      ? "Courier booking retry scheduled"
                      : session.shipment_job?.status === "failed"
                        ? "Courier booking failed"
                        : session.shipment_job?.status === "processing"
                          ? "Booking courier…"
                          : "Courier booking queued"}
                  </span>
                  {user?.is_manager && session.shipment_job?.error && (
                    <p className="mt-2 text-xs text-red-600 dark:text-red-400">
                      {session.shipment_job.error}
                    </p>
                  )}
                </div>
              )}
              <p className="mt-2 text-xs text-zinc-500">
                Booking and tracking notifications are durable worker jobs; no
                manual airway-bill entry is required.
              </p>
            </div>
          )}

          {pollStopped && hasActiveAutomation(session) && (
            <button
              onClick={async () => {
                pollAttempts.current = 0;
                setPollStopped(false);
                setPollCycle((cycle) => cycle + 1);
                setSession(await packing.get(session.id));
              }}
              className="rounded-md border border-zinc-300 px-3 py-2 text-sm font-medium hover:bg-zinc-100 dark:border-zinc-700 dark:hover:bg-zinc-800"
            >
              Refresh automation status
            </button>
          )}

          <Link
            href="/packing"
            className="inline-block rounded-md bg-zinc-900 px-4 py-2 text-sm font-semibold text-white hover:bg-zinc-700 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-300"
          >
            Back to queue
          </Link>
        </div>
      ) : (
        <>
          {/* Scan input */}
          <div className="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
            <form
              onSubmit={(e) => {
                e.preventDefault();
                submitScan(input);
              }}
            >
              <label className="mb-1 block text-xs font-medium uppercase tracking-wide text-zinc-500">
                Scan item barcode
              </label>
              <input
                ref={inputRef}
                autoFocus
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="Scan or type a barcode, then Enter…"
                className="w-full rounded-md border border-zinc-300 bg-white px-4 py-3 font-mono text-lg outline-none focus:border-zinc-900 dark:border-zinc-700 dark:bg-zinc-950 dark:focus:border-zinc-100"
              />
            </form>
            <div className="mt-3 flex flex-wrap items-center gap-2 text-xs">
              <span className="text-zinc-400">Demo aids:</span>
              <button
                onClick={simulateCorrect}
                className="rounded-md border border-zinc-300 px-2.5 py-1 font-medium text-zinc-700 hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-800"
              >
                ▶ Simulate correct scan
              </button>
              <button
                onClick={() => submitScan("0000000000000")}
                className="rounded-md border border-red-300 px-2.5 py-1 font-medium text-red-700 hover:bg-red-50 dark:border-red-900 dark:text-red-300 dark:hover:bg-red-950"
              >
                ✕ Simulate wrong item
              </button>
            </div>
          </div>

          {error && (
            <div className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950 dark:text-red-300">
              {error}
            </div>
          )}

          {/* Packing checklist */}
          <div className="overflow-hidden rounded-xl border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
            <div className="border-b border-zinc-200 px-4 py-3 text-xs font-semibold uppercase tracking-wide text-zinc-500 dark:border-zinc-800">
              Packing list
            </div>
            <ul className="divide-y divide-zinc-100 dark:divide-zinc-800">
              {session.lines.map((l) => (
                <li
                  key={l.line_id}
                  className={`flex items-center justify-between gap-3 px-4 py-3 ${
                    l.complete ? "bg-emerald-50/60 dark:bg-emerald-950/30" : ""
                  }`}
                >
                  <div className="flex items-center gap-3">
                    <span
                      className={`flex h-6 w-6 items-center justify-center rounded-full text-sm ${
                        l.complete
                          ? "bg-emerald-500 text-white"
                          : "border border-zinc-300 text-transparent dark:border-zinc-700"
                      }`}
                    >
                      ✓
                    </span>
                    <div>
                      <div className="font-medium">{l.product_name}</div>
                      <div className="font-mono text-xs text-zinc-500">
                        {l.sku}
                        {l.barcode ? ` · ${l.barcode}` : " · no barcode"}
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="tabular-nums text-sm font-semibold">
                      {l.scanned}/{l.required}
                    </span>
                    {!l.has_barcode && !l.complete && (
                      <button
                        onClick={() => confirmLine(l.line_id)}
                        className="rounded-md border border-zinc-300 px-2.5 py-1 text-xs font-medium hover:bg-zinc-100 dark:border-zinc-700 dark:hover:bg-zinc-800"
                      >
                        Confirm manually
                      </button>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          </div>

          {/* Complete */}
          <div className="flex items-center justify-between">
            <p className="text-sm text-zinc-500">
              {session.complete
                ? "All items verified."
                : "Scan every item to enable completion."}
            </p>
            <button
              disabled={!session.complete || busy}
              onClick={onComplete}
              className="rounded-md bg-emerald-600 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-emerald-500 disabled:opacity-40"
            >
              {busy ? "Completing…" : "Complete pack"}
            </button>
          </div>

          {/* Scan history */}
          {session.recent_scans.length > 0 && (
            <div className="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
              <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-500">
                Recent scans
              </div>
              <div className="flex flex-wrap gap-2">
                {session.recent_scans.map((s) => (
                  <span
                    key={s.id}
                    title={s.result_display}
                    className={`rounded-md px-2 py-1 font-mono text-xs ${
                      s.result === "ok"
                        ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300"
                        : s.result === "overscan"
                          ? "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300"
                          : "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300"
                    }`}
                  >
                    {s.manual ? "(manual)" : s.barcode || "—"} · {s.result}
                  </span>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
