import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "./cn";

/** A light work surface: tables, forms, reference data. */
export function Panel({
  title,
  eyebrow,
  description,
  icon: Icon,
  actions,
  children,
  className,
  bodyClassName,
}: {
  title?: string;
  eyebrow?: string;
  description?: string;
  icon?: LucideIcon;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
}) {
  const hasHeader = title || eyebrow || actions;
  return (
    <section
      className={cn(
        "overflow-hidden rounded-xl border border-subtle bg-raised shadow-card",
        className,
      )}
    >
      {hasHeader ? (
        <header className="flex flex-wrap items-center justify-between gap-3 border-b border-subtle px-5 py-3.5">
          <div className="flex min-w-0 items-center gap-2.5">
            {Icon ? (
              <Icon aria-hidden className="size-4 shrink-0 text-muted" />
            ) : null}
            <div className="min-w-0">
              {eyebrow ? (
                <div className="eyebrow text-muted">{eyebrow}</div>
              ) : null}
              {title ? (
                <h2
                  className={cn(
                    "truncate text-sm font-semibold text-primary",
                    eyebrow && "mt-1",
                  )}
                >
                  {title}
                </h2>
              ) : null}
              {description ? (
                <p className="mt-0.5 text-xs text-secondary">{description}</p>
              ) : null}
            </div>
          </div>
          {actions ? (
            <div className="flex items-center gap-2">{actions}</div>
          ) : null}
        </header>
      ) : null}
      <div className={bodyClassName}>{children}</div>
    </section>
  );
}

/**
 * A dark instrument surface — stays dark in light mode on purpose. Reserved
 * for *live operational signal*, never for ordinary data, so that "this is
 * the machine talking" becomes a visual category the eye learns once.
 */
export function InstrumentPanel({
  eyebrow,
  title,
  status,
  children,
  className,
}: {
  eyebrow?: string;
  title?: string;
  status?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section
      className={cn(
        "overflow-hidden rounded-xl border border-instrument-border bg-instrument text-instrument-text shadow-raised",
        className,
      )}
    >
      {eyebrow || title || status ? (
        <header className="flex flex-wrap items-center justify-between gap-3 border-b border-instrument-border px-5 py-3.5">
          <div className="min-w-0">
            {eyebrow ? (
              <div className="eyebrow text-instrument-muted">{eyebrow}</div>
            ) : null}
            {title ? (
              <h2 className="mt-1 truncate text-sm font-semibold text-instrument-text">
                {title}
              </h2>
            ) : null}
          </div>
          {status}
        </header>
      ) : null}
      {children}
    </section>
  );
}
