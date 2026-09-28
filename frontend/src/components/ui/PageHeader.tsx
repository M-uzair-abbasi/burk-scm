import type { ReactNode } from "react";

/**
 * Every page gets a title AND a one-line statement of what the screen is for.
 * The description is not optional by accident — a screen that can't explain
 * itself in one line is a screen a new operator will bounce off.
 */
export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description: string;
  actions?: ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
      <div className="min-w-0">
        <h1 className="text-[22px] font-semibold tracking-tight text-primary">
          {title}
        </h1>
        <p className="mt-1 max-w-2xl text-sm leading-relaxed text-secondary">
          {description}
        </p>
      </div>
      {actions ? (
        <div className="flex shrink-0 items-center gap-2">{actions}</div>
      ) : null}
    </div>
  );
}
