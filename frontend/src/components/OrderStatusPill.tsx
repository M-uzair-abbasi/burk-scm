import type { OrderStatus } from "@/lib/types";

const STYLES: Record<OrderStatus, string> = {
  pending: "bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300",
  confirmed: "bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-300",
  packed: "bg-violet-100 text-violet-700 dark:bg-violet-950 dark:text-violet-300",
  shipped: "bg-sky-100 text-sky-700 dark:bg-sky-950 dark:text-sky-300",
  delivered:
    "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300",
  cancelled: "bg-zinc-100 text-zinc-500 line-through dark:bg-zinc-800",
  returned: "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300",
};

/** Coloured pill for a sales order's normalized status. */
export function OrderStatusPill({
  status,
  label,
}: {
  status: OrderStatus;
  label?: string;
}) {
  return (
    <span
      className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${
        STYLES[status] ?? STYLES.pending
      }`}
    >
      {label ?? status}
    </span>
  );
}
