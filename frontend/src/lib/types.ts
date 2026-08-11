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
  quantity_ordered: number;
  unit_price: string;
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
  subtotal?: string;
  shipping_fee?: string;
  raw_payload?: Record<string, unknown>;
  lines?: SalesOrderLine[];
  // Present only on the detail endpoint — Module 4/5/6 dispatch history.
  notifications?: NotificationRecord[];
  shipment?: Shipment | null;
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
}

export interface QueueIntegrity {
  dropped: number;
  duplicated: number;
  unique: number;
  ok: boolean;
  dropped_detail: { channel: string; external_id: string }[];
  duplicated_detail: { channel: string; external_id: string; count: number }[];
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
  runs: SyncRun[];
  summary: OrderSummary;
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
}

export interface ScanResponse {
  scan: PackScan;
  session: PackSession;
}

// --- Module 4: video surveillance + Module 5/6 notification ledger ---

export type RecordingStatus =
  | "pending"
  | "recording"
  | "processing"
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
  sealed_at: string;
  captured_at: string | null;
  compressed_at: string | null;
  error: string;
}

export type NotificationKind =
  | "packaging_video"
  | "shipment_tracking"
  | "review_request";
export type NotificationChannelType = "email" | "whatsapp";
export type NotificationDeliveryStatus = "scheduled" | "sent" | "failed";

export interface NotificationRecord {
  id: number;
  kind: NotificationKind;
  kind_display: string;
  channel: NotificationChannelType;
  channel_display: string;
  recipient: string;
  status: NotificationDeliveryStatus;
  status_display: string;
  reference_event_at: string;
  scheduled_for: string | null;
  sent_at: string | null;
  latency_seconds: number | null;
  payload: Record<string, unknown>;
  error: string;
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
  label_url: string;
  booked_at: string;
  in_transit_at: string | null;
  delivered_at: string | null;
  events: ShipmentEvent[];
}
