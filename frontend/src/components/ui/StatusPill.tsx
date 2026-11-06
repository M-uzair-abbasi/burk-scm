import type { ReactNode } from "react";

import { cn } from "./cn";
import type { PillVariant, StatusLook, Tone } from "./status";

const SOFT: Record<Tone, string> = {
  neutral: "bg-neutral-soft text-neutral-text",
  success: "bg-success-soft text-success-text",
  warning: "bg-warning-soft text-warning-text",
  critical: "bg-critical-soft text-critical-text",
};

const SOLID: Record<Tone, string> = {
  neutral: "bg-neutral-signal text-white",
  success: "bg-success text-white",
  warning: "bg-warning text-white",
  critical: "bg-critical text-white",
};

const OUTLINE: Record<Tone, string> = {
  neutral: "border border-neutral-signal/45 text-neutral-text bg-transparent",
  success: "border border-success/45 text-success-text bg-transparent",
  warning: "border border-warning/45 text-warning-text bg-transparent",
  critical: "border border-critical/45 text-critical-text bg-transparent",
};

function look(tone: Tone, variant: PillVariant): string {
  if (variant === "solid") return SOLID[tone];
  if (variant === "outline") return OUTLINE[tone];
  return SOFT[tone];
}

/**
 * The single pill used for every status in the app. Callers pass a
 * {tone, variant} pair from `status.ts` rather than choosing colours, which
 * is what keeps a colour meaning the same thing on every screen.
 */
export function StatusPill({
  children,
  tone = "neutral",
  variant = "soft",
  className,
}: {
  children: ReactNode;
  tone?: Tone;
  variant?: PillVariant;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium",
        look(tone, variant),
        className,
      )}
    >
      {children}
    </span>
  );
}

/** Convenience wrapper for the `Record<Status, StatusLook>` maps. */
export function LookPill({
  look: l,
  children,
  className,
}: {
  look: StatusLook;
  children: ReactNode;
  className?: string;
}) {
  return (
    <StatusPill tone={l.tone} variant={l.variant} className={className}>
      {children}
    </StatusPill>
  );
}

/**
 * Sales channel is an *origin*, not a status, so it must not borrow a status
 * colour — it renders as a neutral chip with a small identifying dot.
 */
export function ChannelTag({
  channel,
  label,
}: {
  channel: "burk" | "daraz";
  label: string;
}) {
  return (
    <span className="inline-flex items-center gap-1.5 whitespace-nowrap rounded-full bg-sunken px-2 py-0.5 text-xs font-medium text-secondary">
      <span
        aria-hidden
        className={cn(
          "size-1.5 rounded-full",
          channel === "burk" ? "bg-channel-burk" : "bg-channel-daraz",
        )}
      />
      {label}
    </span>
  );
}
