"use client";

import { useEffect, useState } from "react";

import { dashboard, health, packing } from "@/lib/resources";

export interface OpsCounts {
  /** Orders sitting in the packing queue — the main "work waiting" figure. */
  packQueue: number;
  lowStock: number;
  openPOs: number;
  /** null while unknown, so the shell can avoid claiming health it hasn't checked. */
  healthOk: boolean | null;
  /**
   * False once the health endpoint has refused us. It is manager-only, so an
   * operator would otherwise stare at a lamp stuck on "checking" forever —
   * the shell hides the lamp entirely instead of implying a stalled system.
   */
  healthAvailable: boolean;
}

const EMPTY: OpsCounts = {
  packQueue: 0,
  lowStock: 0,
  openPOs: 0,
  healthOk: null,
  healthAvailable: true,
};

/**
 * Live counts for the sidebar badges and the topbar status lamp.
 *
 * Every call is settled independently: an operator has no permission for the
 * supplier/PO endpoints, and a 403 there must not blank out the packing count
 * they do need. Poll is slow (30s) because none of these drive an action on
 * their own — they only tell you where to look.
 */
export function useOpsCounts(): OpsCounts {
  const [counts, setCounts] = useState<OpsCounts>(EMPTY);

  useEffect(() => {
    let alive = true;

    async function load() {
      const [queue, summary, healthResult] = await Promise.allSettled([
        packing.queue(),
        dashboard.summary(),
        health.get(),
      ]);
      if (!alive) return;

      setCounts((prev) => ({
        packQueue:
          queue.status === "fulfilled" ? queue.value.length : prev.packQueue,
        lowStock:
          summary.status === "fulfilled"
            ? summary.value.low_stock_count
            : prev.lowStock,
        openPOs:
          summary.status === "fulfilled"
            ? summary.value.open_po_count
            : prev.openPOs,
        healthOk:
          healthResult.status === "fulfilled"
            ? healthResult.value.ok
            : prev.healthOk,
        healthAvailable:
          healthResult.status === "fulfilled" ? true : false,
      }));
    }

    load();
    const timer = setInterval(load, 30_000);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, []);

  return counts;
}
