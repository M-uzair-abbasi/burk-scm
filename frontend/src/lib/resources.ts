/**
 * Typed wrappers over apiFetch, one per REST resource. Pages import these
 * rather than hand-writing URLs, so the endpoint contract lives in one place.
 */

import { apiFetch } from "./api";
import type {
  Category,
  DashboardSummary,
  OrderSummary,
  Paginated,
  Product,
  PurchaseOrder,
  SalesOrder,
  StockMovement,
  Supplier,
  SupplierProduct,
  SyncResponse,
} from "./types";

type Query = Record<string, string | number | boolean | undefined | null>;

function qs(params?: Query): string {
  if (!params) return "";
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") {
      search.set(key, String(value));
    }
  }
  const s = search.toString();
  return s ? `?${s}` : "";
}

export const products = {
  list: (params?: Query) =>
    apiFetch<Paginated<Product>>(`/api/products/${qs(params)}`),
  get: (id: number) => apiFetch<Product>(`/api/products/${id}/`),
  create: (body: Partial<Product>) =>
    apiFetch<Product>("/api/products/", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  update: (id: number, body: Partial<Product>) =>
    apiFetch<Product>(`/api/products/${id}/`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
};

export const categories = {
  list: () => apiFetch<Paginated<Category>>("/api/categories/"),
};

export const movements = {
  list: (productId?: number) =>
    apiFetch<Paginated<StockMovement>>(
      `/api/stock-movements/${qs({ product: productId })}`,
    ),
  create: (body: {
    product: number;
    quantity_delta: number;
    reason: string;
    note?: string;
    allow_negative?: boolean;
  }) =>
    apiFetch<StockMovement>("/api/stock-movements/", {
      method: "POST",
      body: JSON.stringify(body),
    }),
};

export const dashboard = {
  summary: () => apiFetch<DashboardSummary>("/api/dashboard/summary/"),
};

export const suppliers = {
  list: (params?: Query) =>
    apiFetch<Paginated<Supplier>>(`/api/suppliers/${qs(params)}`),
  get: (id: number) => apiFetch<Supplier>(`/api/suppliers/${id}/`),
};

export const supplierProducts = {
  list: (params?: Query) =>
    apiFetch<Paginated<SupplierProduct>>(`/api/supplier-products/${qs(params)}`),
};

export const orders = {
  list: (params?: Query) =>
    apiFetch<Paginated<SalesOrder>>(`/api/orders/${qs(params)}`),
  get: (id: number) => apiFetch<SalesOrder>(`/api/orders/${id}/`),
  summary: () => apiFetch<OrderSummary>("/api/orders/summary/"),
  // "Sync now": pull every channel feed into the queue. Returns the per-channel
  // SyncRuns plus a fresh summary so the reconciliation strip updates in one trip.
  sync: () =>
    apiFetch<SyncResponse>("/api/orders/sync/", {
      method: "POST",
      body: JSON.stringify({}),
    }),
};

export const purchaseOrders = {
  list: (params?: Query) =>
    apiFetch<Paginated<PurchaseOrder>>(`/api/purchase-orders/${qs(params)}`),
  get: (id: number) => apiFetch<PurchaseOrder>(`/api/purchase-orders/${id}/`),
  reorder: (body: { product: number; quantity?: number; supplier?: number }) =>
    apiFetch<PurchaseOrder>("/api/purchase-orders/reorder/", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  submit: (id: number) =>
    apiFetch<PurchaseOrder>(`/api/purchase-orders/${id}/submit/`, {
      method: "POST",
      body: JSON.stringify({}),
    }),
  receive: (id: number, receipts?: { line: number; quantity: number }[]) =>
    apiFetch<PurchaseOrder>(`/api/purchase-orders/${id}/receive/`, {
      method: "POST",
      body: JSON.stringify(receipts ? { receipts } : {}),
    }),
};
