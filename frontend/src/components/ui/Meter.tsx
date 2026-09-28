import { cn } from "./cn";
import type { Tone } from "./status";

const FILL: Record<Tone, string> = {
  neutral: "bg-neutral-signal",
  success: "bg-success",
  warning: "bg-warning",
  critical: "bg-critical",
};

/** Proportional bar — stock against safety level, scans against required. */
export function Meter({
  value,
  max,
  tone = "neutral",
  className,
  label,
}: {
  value: number;
  max: number;
  tone?: Tone;
  className?: string;
  label?: string;
}) {
  const pct = max > 0 ? Math.min(100, Math.round((value / max) * 100)) : 0;
  return (
    <div
      className={cn(
        "h-1.5 w-full overflow-hidden rounded-full bg-sunken",
        className,
      )}
      role="progressbar"
      aria-valuenow={value}
      aria-valuemin={0}
      aria-valuemax={max}
      aria-label={label}
    >
      <div
        className={cn(
          "h-full rounded-full transition-[width] duration-500",
          FILL[tone],
        )}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}
