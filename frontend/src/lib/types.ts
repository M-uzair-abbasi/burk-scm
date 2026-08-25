/**
 * Shapes returned by the Django REST API. Money and other DecimalFields are
 * serialised by DRF as strings ("1820.00"), never numbers — keep them as
 * strings and format at the display edge so precision is never lost.
 */

export interface Paginated<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export type Unit = "pcs" | "kg" | "ltr" | "box";

export interface Category {
  id: number;
  name: string;
  slug: string;
  parent: number | null;
  product_count: number;
}

export interface Product {
  id: number;
  sku: string;
  barcode: string | null;
  name: string;
  category: number | null;
  category_name: string | null;
  unit: Unit;
  unit_display: string;
  quantity_on_hand: number;
  safety_stock: number;
  reorder_quantity: number;
  cost_price: string | null;
  is_active: boolean;
  is_low_stock: boolean;
  created_at: string;
  updated_at: string;
}

export type MovementReason =
  | "initial"
  | "purchase_receipt"
  | "sale"
  | "return"
  | "damage"
  | "adjustment";

export interface StockMovement {
  id: number;
  product: number;
  product_sku: string;
  product_name: string;
  quantity_delta: number;
  reason: MovementReason;
  reason_display: string;
  purchase_order: number | null;
  note: string;
  created_by: number | null;
  created_by_username: string | null;
  created_at: string;
}

export interface PriceTier {
  id: number;
  supplier_product: number;
  min_quantity: number;
  unit_price: string;
}

export interface SupplierProduct {
  id: number;
  supplier: number;
  supplier_name: string;
  product: number;
  product_sku: string;
  product_name: string;
  supplier_sku: string;
  lead_time_days: number | null;
  effective_lead_time_days: number;
  is_preferred: boolean;
  is_active: boolean;
  price_tiers: PriceTier[];
}

export interface Supplier {
  id: number;
  code: string;
  name: string;
  contact_person: string;
  email: string;
  phone: string;
  address: string;
  city: string;
  default_lead_time_days: number;
  payment_terms: string;
  is_active: boolean;
  notes: string;
  product_count: number;
  created_at: string;
  updated_at: string;
}

export type POStatus =
  | "draft"
  | "submitted"
  | "partially_received"
  | "received"
  | "cancelled";

export interface PurchaseOrderLine {
  id: number;
  product: number;
  product_sku: string;
  product_name: string;
  supplier_product: number | null;
  quantity_ordered: number;
  unit_price: string;
  effective_lead_time_days: number;
  price_tier_min_quantity: number | null;
  quantity_received: number;
  quantity_outstanding: number;
  line_total: string;
}

export interface PurchaseOrder {
  id: number;
  po_number: string;
  supplier: number;
  supplier_name: string;
  status: POStatus;
  status_display: string;
  expected_date: string | null;
  notes: string;
  created_by: number | null;
  created_by_username: string | null;
  lines: PurchaseOrderLine[];
  total_amount: string;
  is_open: boolean;
  created_at: string;
  updated_at: string;
  submitted_at: string | null;
  received_at: string | null;
}

export interface DashboardSummary {
  total_skus: number;
  low_stock_count: number;
  out_of_stock_count: number;
  open_po_count: number;
}

// --- Module 2: Multi-channel order aggregation ---

export type OrderChannel = "burk" | "daraz";

export type OrderStatus =
  | "pending"
  | "confirmed"
  | "packed"
  | "shipped"
  | "delivered"
  | "cancelled"
  | "returned";

export interface SalesOrderLine {
  id: number;
  sku: string;
  product: number | null;
  product_sku: string | null;
  product_name: string;
  quantity: number;
  unit_price: string;
  line_total: string;
}

export interface SalesOrder {
  id: number;
  reference: string;
  channel: OrderChannel;
  channel_display: string;
  external_id: string;
  status: OrderStatus;
  status_display: string;
  source_status: OrderStatus;
  source_status_display: string;
  customer_name: string;
  item_count: number;
  currency: string;
  total: string;
  placed_at: string | null;
  ingested_at: string;
  last_synced_at: string | null;
  // Present only on the detail endpoint:
  customer_phone?: string;
  customer_email?: string;
  shipping_address?: string;
  shipping_address_line1?: string;
  shipping_address_line2?: string;
  shipping_city?: string;
  shipping_province?: string;
  shipping_postal_code?: string;
  shipping_country?: string;
  customer_instructions?: string;
  parcel_weight_kg?: string;
  parcel_length_cm?: string;
  parcel_width_cm?: string;
  parcel_height_cm?: string;
  cod_amount?: string;
  payment_mode?: "prepaid" | "cod";
  shipping_service_type?: string;
  pickup_account?: string;
  subtotal?: string;
  shipping_fee?: string;
  raw_payload?: Record<string, unknown>;
  lines?: SalesOrderLine[];
  // Present only on the detail endpoint — Module 4/5/6 dispatch history.
  notifications?: NotificationRecord[];
  shipment?: Shipment | null;
  shipment_job?: ShipmentJob | null;
}

export interface SyncRun {
  id: number;
  channel: OrderChannel;
  channel_display: string;
  started_at: string;
  finished_at: string | null;
  fetched: number;
  created: number;
  updated: number;
  duplicates_skipped: number;
  failed: number;
  ok: boolean;
  reconciled: boolean;
  detail: {
    fetch_error?: string;
    errors?: { record_index?: number; external_id?: string; error: string }[];
  };
}

export interface QueueIntegrity {
  dropped: number;
  stale: number;
  duplicated: number;
  mismatched: number;
  unique: number;
  ok: boolean;
  required_channels: string[];
  channels_checked: number;
  channels_checked_detail: string[];
  inspected_records: number;
  channel_errors: {
    channel: string;
    stage: string;
    error: string;
    external_id?: string;
  }[];
  dropped_detail: { channel: string; external_id: string }[];
  stale_detail: { channel: string; external_id: string }[];
  duplicated_detail: { channel: string; external_id: string; count: number }[];
  mismatched_detail: {
    channel: string;
    external_id: string;
    fields: string[];
  }[];
}

export interface ChannelSummary {
  label: string;
  count: number;
  last_sync: string | null;
  last_run: SyncRun | null;
}

export interface OrderSummary {
  total_orders: number;
  by_channel: Record<string, ChannelSummary>;
  by_status: Record<string, number>;
  integrity: QueueIntegrity;
  recent_runs: SyncRun[];
}

export interface SyncResponse {
  overall_ok: boolean;
  runs: SyncRun[];
  summary: OrderSummary;
  detail: string;
}

// --- Module 3: Fulfilment / barcode verification ---

export interface PackQueueOrder {
  id: number;
  reference: string;
  channel: OrderChannel;
  channel_display: string;
  external_id: string;
  customer_name: string;
  item_count: number;
  total: string;
  placed_at: string | null;
  status: OrderStatus;
  status_display: string;
}

export type ScanResult = "ok" | "mismatch" | "overscan";

export interface PackScan {
  id: number;
  barcode: string;
  result: ScanResult;
  result_display: string;
  product: number | null;
  product_name: string | null;
  line: number | null;
  manual: boolean;
  scanned_at: string;
}

export interface PackLine {
  line_id: number;
  sku: string;
  product_name: string;
  barcode: string | null;
  has_barcode: boolean;
  required: number;
  scanned: number;
  complete: boolean;
}

export type PackSessionStatus = "in_progress" | "completed" | "cancelled";

export interface PackSession {
  id: number;
  status: PackSessionStatus;
  status_display: string;
  complete: boolean;
  started_at: string;
  completed_at: string | null;
  order: {
    id: number;
    reference: string;
    channel: OrderChannel;
    channel_display: string;
    external_id: string;
    customer_name: string;
    status: OrderStatus;
  };
  lines: PackLine[];
  recent_scans: PackScan[];
  recording: PackagingRecording | null;
  video_notifications: NotificationRecord[];
  shipment: Shipment | null;
  shipment_job: ShipmentJob | null;
}

export interface ScanResponse {
  scan: PackScan;
  session: PackSession;
}

// --- Module 4: video surveillance + Module 5/6 notification ledger ---

export type RecordingStatus =
  | "pending"
  | "recording"
  | "queued"
  | "processing"
  | "retrying"
  | "ready"
  | "failed";

export interface PackagingRecording {
  id: number;
  status: RecordingStatus;
  status_display: string;
  video_url: string | null;
  duration_seconds: number | null;
  raw_size_bytes: number | null;
  compressed_size_bytes: number | null;
  raw_checksum: string;
  compressed_checksum: string;
  sealed_at: string | null;
  capture_started_at: string | null;
  capture_stopped_at: string | null;
  captured_at: string | null;
  compressed_at: string | null;
  processing_attempts: number;
  next_attempt_at: string | null;
  error: string;
  terminal_error_class: string;
  raw_deleted_at: string | null;
  compressed_deleted_at: string | null;
}

export type NotificationKind =
  | "packaging_video"
  | "shipment_tracking"
  | "review_request";
export type NotificationChannelType = "email" | "whatsapp";
export type NotificationDeliveryStatus =
  | "scheduled"
  | "processing"
  | "retrying"
  | "accepted"
  | "sent"
  | "failed";

export interface NotificationRecord {
  id: number;
  kind: NotificationKind;
  kind_display: string;
  channel: NotificationChannelType;
  channel_display: string;
  idempotency_key: string;
  recipient: string;
  status: NotificationDeliveryStatus;
  status_display: string;
  reference_event_at: string;
  scheduled_for: string | null;
  next_attempt_at: string | null;
  sent_at: string | null;
  acknowledged_at: string | null;
  attempt_count: number;
  provider_message_id: string;
  latency_seconds: number | null;
  payload: Record<string, unknown>;
  error: string;
  terminal_error_class: string;
  created_at: string;
}

// --- Module 5: logistics + Module 6's delivery trigger ---

export type Courier = "leopard" | "tcs" | "trax" | "mnp";
export type ShipmentStatus = "booked" | "in_transit" | "delivered";

export interface ShipmentEvent {
  id: number;
  status: ShipmentStatus;
  status_display: string;
  occurred_at: string;
  source: string;
}

export interface Shipment {
  id: number;
  courier: Courier;
  courier_display: string;
  status: ShipmentStatus;
  status_display: string;
  tracking_number: string;
  provider_booking_id: string | null;
  request_idempotency_key: string;
  label_reference: string;
  label_url: string;
  booked_at: string;
  in_transit_at: string | null;
  delivered_at: string | null;
  events: ShipmentEvent[];
}

export type WorkStatus =
  | "pending"
  | "processing"
  | "retry"
  | "succeeded"
  | "failed";

export interface ShipmentJob {
  status: WorkStatus;
  attempts: number;
  max_attempts: number;
  next_attempt_at: string | null;
  error: string;
  completed_at: string | null;
}

export interface OperationalHealth {
  ok: boolean;
  checked_at: string;
  components: {
    app: { ok: boolean };
    database: { ok: boolean; error_class?: string };
    worker: {
      ok: boolean;
      name?: string;
      age_seconds: number | null;
      last_claimed?: number;
      last_succeeded?: number;
      last_failed?: number;
      detail?: string;
    };
    backlog: {
      ok: boolean;
      due: number;
      oldest_due_age_seconds: number;
      failed: number;
      processing: number;
    };
    media: {
      ok: boolean;
      exists: boolean;
      writable: boolean;
      free_bytes: number;
      retention_policy_ok: boolean;
    };
    adapters: {
      ok: boolean;
      live_required: boolean;
      all_live: boolean;
      details: {
        name: string;
        ok: boolean;
        mode: string;
        error_class?: string;
      }[];
    };
  };
}

export interface OperationalMetrics {
  ok: boolean;
  checked_at: string;
  window: { hours: number; starts_at: string };
  queue: {
    active: number;
    due: number;
    retrying: number;
    failed: number;
    processing: number;
    oldest_due_age_seconds: number;
  };
  sources: {
    channels: {
      channel: "burk" | "daraz";
      last_finished_at: string | null;
      lag_seconds: number | null;
      failed_runs: number;
    }[];
    missing: string[];
    max_lag_seconds: number | null;
    failed_runs: number;
  };
  packing: {
    scans: number;
    mismatches_intercepted: number;
    overscans_intercepted: number;
  };
  notifications: {
    total: number;
    acknowledged: number;
    awaiting_acknowledgement: number;
    failed: number;
    average_latency_seconds: number | null;
    max_latency_seconds: number | null;
  };
  shipments: { booking_failures: number };
  media: {
    total: number;
    processed: number;
    failed: number;
    average_processing_seconds: number | null;
    max_processing_seconds: number | null;
  };
  thresholds: Record<string, number>;
  breaches: {
    code: string;
    value: number | null;
    threshold: number | string;
  }[];
}
