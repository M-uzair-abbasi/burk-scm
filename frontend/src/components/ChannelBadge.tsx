import type { OrderChannel } from "@/lib/types";

const STYLES: Record<OrderChannel, string> = {
  burk: "bg-indigo-100 text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300",
  daraz: "bg-orange-100 text-orange-700 dark:bg-orange-950 dark:text-orange-300",
};

/** Coloured pill identifying which sales channel an order came from. */
export function ChannelBadge({
  channel,
  label,
}: {
  channel: OrderChannel;
  label?: string;
}) {
  return (
    <span
      className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${
        STYLES[channel] ?? "bg-zinc-100 text-zinc-600"
      }`}
    >
      {label ?? channel}
    </span>
  );
}
