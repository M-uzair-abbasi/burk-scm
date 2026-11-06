"use client";

/**
 * Module 4, browser-camera capture: records from the packer's own device
 * instead of dedicated overhead hardware. Recording starts as soon as this
 * mounts (i.e. as soon as packing starts) and keeps running locally in the
 * browser -- nothing is uploaded until the parent calls stopAndCollect(),
 * which the packing page does right before sealing the pack.
 */

import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
} from "react";
import { Video } from "lucide-react";

export interface PackagingCameraRecorderHandle {
  /** Stops the recorder and resolves the finished clip, or null if no
   * recording was ever active (camera permission was never granted). */
  stopAndCollect(): Promise<{ blob: Blob; filename: string } | null>;
}

const MIME_CANDIDATES = [
  "video/webm;codecs=vp8",
  "video/webm",
  "video/mp4",
];

function pickMimeType(): string | undefined {
  if (typeof MediaRecorder === "undefined") return undefined;
  return MIME_CANDIDATES.find((type) => MediaRecorder.isTypeSupported(type));
}

function filenameFor(mimeType: string): string {
  return mimeType.includes("mp4") ? "packaging.mp4" : "packaging.webm";
}

type RecorderState = "starting" | "recording" | "error";

export const PackagingCameraRecorder = forwardRef<
  PackagingCameraRecorderHandle,
  { active: boolean }
>(function PackagingCameraRecorder({ active }, ref) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const [state, setState] = useState<RecorderState>("starting");
  const [error, setError] = useState<string | null>(null);
  const [retryTick, setRetryTick] = useState(0);

  useEffect(() => {
    if (!active) return;
    let cancelled = false;

    async function start() {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          video: true,
          audio: false,
        });
        if (cancelled) {
          stream.getTracks().forEach((track) => track.stop());
          return;
        }
        streamRef.current = stream;
        if (videoRef.current) videoRef.current.srcObject = stream;

        const mimeType = pickMimeType();
        const recorder = new MediaRecorder(
          stream,
          mimeType ? { mimeType } : undefined,
        );
        chunksRef.current = [];
        recorder.ondataavailable = (event) => {
          if (event.data.size > 0) chunksRef.current.push(event.data);
        };
        recorder.start();
        recorderRef.current = recorder;
        setState("recording");
      } catch {
        if (!cancelled) {
          setError(
            "Camera access was blocked or no camera is available on this device.",
          );
          setState("error");
        }
      }
    }
    start();

    return () => {
      cancelled = true;
      if (recorderRef.current && recorderRef.current.state !== "inactive") {
        recorderRef.current.stop();
      }
      streamRef.current?.getTracks().forEach((track) => track.stop());
    };
  }, [active, retryTick]);

  useImperativeHandle(ref, () => ({
    stopAndCollect: () =>
      new Promise((resolve) => {
        const recorder = recorderRef.current;
        if (!recorder || recorder.state === "inactive") {
          resolve(null);
          return;
        }
        recorder.onstop = () => {
          const mimeType = recorder.mimeType || "video/webm";
          const blob = new Blob(chunksRef.current, { type: mimeType });
          streamRef.current?.getTracks().forEach((track) => track.stop());
          resolve({ blob, filename: filenameFor(mimeType) });
        };
        recorder.stop();
      }),
  }));

  if (!active) return null;

  if (state === "error") {
    return (
      <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-warning/30 bg-warning-soft px-4 py-2.5 text-sm text-warning-text">
        <span>{error}</span>
        <button
          type="button"
          onClick={() => setRetryTick((tick) => tick + 1)}
          className="font-semibold underline underline-offset-2"
        >
          Retry camera access
        </button>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-3 rounded-lg border border-subtle bg-sunken p-2.5">
      <video
        ref={videoRef}
        autoPlay
        muted
        playsInline
        className="h-16 w-24 rounded object-cover"
      />
      <div className="flex items-center gap-1.5 text-xs text-secondary">
        <Video aria-hidden className="size-3.5" />
        {state === "recording" ? (
          <span className="flex items-center gap-1.5">
            <span className="size-1.5 animate-pulse rounded-full bg-critical" />
            Recording the packaging video
          </span>
        ) : (
          "Starting the camera…"
        )}
      </div>
    </div>
  );
});
