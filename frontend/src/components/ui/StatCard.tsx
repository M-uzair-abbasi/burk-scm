import Link from "next/link";
import type { LucideIcon } from "lucide-react";

import { cn } from "./cn";
import type { Tone } from "./status";

const TONE_FIGURE: Record<Tone, string> = {
  neutral: "text-primary",
  success: "text-success",
  warning: "text-warning",
  critical: "text-critical",
};

/**
 * A single headline figure. `href` is encouraged: a number a user can't act
 * on is trivia, and every count on the dashboard has a screen behind it.
 */
export function StatCard({
  label,
  value,
  icon: Icon,
  tone = "neutral",
  caption,
  href,
}: {
  label: string;
  value: string | number;
  icon?: LucideIcon;
  tone?: Tone;
  caption?: string;
  href?: string;
}) {
  const inner = (
    <>
      <div className="flex items-start justify-between gap-2">
        <span className="eyebrow text-muted">{label}</span>
        {Icon ? (
          <Icon
            aria-hidden
            className={cn(
              "size-4 shrink-0",
              tone === "neutral" ? "text-muted" : TONE_FIGURE[tone],
            )}
          />
        ) : null}
      </div>
      <div
        className={cn(
          "tabular mt-3 text-[28px] font-semibold leading-none tracking-tight",
          TONE_FIGURE[tone],
        )}
      >
        {value}
      </div>
      {caption ? (
        <div className="mt-2 text-xs text-secondary">{caption}</div>
      ) : null}
    </>
  );

  const base =
    "block rounded-xl border border-subtle bg-raised p-4 shadow-card transition-colors duration-150";

  if (href) {
    return (
      <Link
        href={href}
        className={cn(base, "hover:border-accent/60 hover:bg-hover")}
      >
        {inner}
      </Link>
    );
  }
  return <div className={base}>{inner}</div>;
}
