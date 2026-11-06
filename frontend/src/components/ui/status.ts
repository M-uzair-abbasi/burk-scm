import type {
  NotificationDeliveryStatus,
  OrderStatus,
  POStatus,
  PackSessionStatus,
  RecordingStatus,
  ScanResult,
  ShipmentStatus,
  WorkStatus,
} from "@/lib/types";

/**
 * The whole colour vocabulary of the app, in four tones.
 *
 * The old UI gave each status its own hue, so a green pill meant "delivered"
 * in one table and "healthy" in another, while purple meant nothing at all.
 * Here a tone means exactly one thing everywhere:
 *
 *   neutral  — inert. Nothing is wrong; nothing is required of you.
 *   success  — done, healthy, within threshold.
 *   warning  — a human needs to look at this soon.
 *   critical — blocked, failed, or a breached threshold.
 *
 * Progress *within* a good path is expressed by the pill's variant (outline =
 * under way, solid = terminal) rather than by inventing more colours.
 */
export type Tone = "neutral" | "success" | "warning" | "critical";
export type PillVariant = "soft" | "solid" | "outline";

export interface StatusLook {
  tone: Tone;
  variant: PillVariant;
}

export const ORDER_STATUS: Record<OrderStatus, StatusLook> = {
  pending: { tone: "neutral", variant: "soft" },
  confirmed: { tone: "neutral", variant: "solid" },
  packed: { tone: "success", variant: "outline" },
  shipped: { tone: "success", variant: "outline" },
  delivered: { tone: "success", variant: "solid" },
  cancelled: { tone: "critical", variant: "outline" },
  returned: { tone: "warning", variant: "solid" },
};

export const PO_STATUS: Record<POStatus, StatusLook> = {
  draft: { tone: "neutral", variant: "soft" },
  submitted: { tone: "neutral", variant: "solid" },
  partially_received: { tone: "warning", variant: "outline" },
  received: { tone: "success", variant: "solid" },
  cancelled: { tone: "critical", variant: "outline" },
};

export const PACK_SESSION_STATUS: Record<PackSessionStatus, StatusLook> = {
  in_progress: { tone: "warning", variant: "outline" },
  completed: { tone: "success", variant: "solid" },
  cancelled: { tone: "critical", variant: "outline" },
};

export const RECORDING_STATUS: Record<RecordingStatus, StatusLook> = {
  pending: { tone: "neutral", variant: "soft" },
  recording: { tone: "warning", variant: "outline" },
  queued: { tone: "neutral", variant: "soft" },
  processing: { tone: "warning", variant: "outline" },
  retrying: { tone: "warning", variant: "solid" },
  ready: { tone: "success", variant: "solid" },
  failed: { tone: "critical", variant: "solid" },
};

export const NOTIFICATION_STATUS: Record<
  NotificationDeliveryStatus,
  StatusLook
> = {
  scheduled: { tone: "neutral", variant: "soft" },
  processing: { tone: "warning", variant: "outline" },
  retrying: { tone: "warning", variant: "solid" },
  accepted: { tone: "success", variant: "outline" },
  sent: { tone: "success", variant: "solid" },
  failed: { tone: "critical", variant: "solid" },
};

export const SHIPMENT_STATUS: Record<ShipmentStatus, StatusLook> = {
  booked: { tone: "neutral", variant: "solid" },
  in_transit: { tone: "success", variant: "outline" },
  delivered: { tone: "success", variant: "solid" },
};

export const WORK_STATUS: Record<WorkStatus, StatusLook> = {
  pending: { tone: "neutral", variant: "soft" },
  processing: { tone: "warning", variant: "outline" },
  retry: { tone: "warning", variant: "solid" },
  succeeded: { tone: "success", variant: "solid" },
  failed: { tone: "critical", variant: "solid" },
};

export const SCAN_RESULT: Record<ScanResult, StatusLook> = {
  ok: { tone: "success", variant: "solid" },
  mismatch: { tone: "critical", variant: "solid" },
  overscan: { tone: "critical", variant: "solid" },
};

/** Stock level against its safety threshold. */
export function stockTone(onHand: number, safety: number): Tone {
  if (onHand <= 0) return "critical";
  if (safety > 0 && onHand <= safety) return "warning";
  return "success";
}

export function stockLabel(onHand: number, safety: number): string {
  if (onHand <= 0) return "Out of stock";
  if (safety > 0 && onHand <= safety) return "Low";
  return "In stock";
}
