import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

/**
 * An empty screen is the worst place to abandon someone, so this primitive
 * makes the useful version the easy version: say what the screen holds, why
 * it's empty, and give a real way forward. `action` is required — if there is
 * genuinely nothing to do, pass an explanatory hint instead via `hint`.
 */
export function EmptyState({
  icon: Icon,
  title,
  body,
  action,
  hint,
}: {
  icon: LucideIcon;
  title: string;
  body: string;
  action?: ReactNode;
  hint?: string;
}) {
  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-strong bg-raised px-6 py-14 text-center">
      <div className="mb-4 flex size-11 items-center justify-center rounded-full bg-sunken text-muted">
        <Icon aria-hidden className="size-5" />
      </div>
      <h3 className="text-[15px] font-semibold text-primary">{title}</h3>
      <p className="mt-1.5 max-w-sm text-sm leading-relaxed text-secondary">
        {body}
      </p>
      {action ? <div className="mt-5">{action}</div> : null}
      {hint ? <p className="mt-4 text-xs text-muted">{hint}</p> : null}
    </div>
  );
}
