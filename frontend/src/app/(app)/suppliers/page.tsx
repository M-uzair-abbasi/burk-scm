"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { suppliers as suppliersApi } from "@/lib/resources";
import type { Supplier } from "@/lib/types";

export default function SuppliersPage() {
  const router = useRouter();
  const [rows, setRows] = useState<Supplier[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    suppliersApi
      .list()
      .then((r) => setRows(r.results))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="overflow-x-auto rounded-xl border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-zinc-200 text-left text-xs uppercase tracking-wide text-zinc-500 dark:border-zinc-800">
            <th className="px-4 py-3 font-medium">Code</th>
            <th className="px-4 py-3 font-medium">Name</th>
            <th className="px-4 py-3 font-medium">City</th>
            <th className="px-4 py-3 font-medium">Contact</th>
            <th className="px-4 py-3 text-right font-medium">Lead time</th>
            <th className="px-4 py-3 text-right font-medium">Products</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-zinc-100 dark:divide-zinc-800">
          {loading ? (
            <tr>
              <td colSpan={6} className="px-4 py-8 text-center text-zinc-500">
                Loading…
              </td>
            </tr>
          ) : rows.length === 0 ? (
            <tr>
              <td colSpan={6} className="px-4 py-8 text-center text-zinc-500">
                No suppliers yet.
              </td>
            </tr>
          ) : (
            rows.map((s) => (
              <tr
                key={s.id}
                onClick={() => router.push(`/suppliers/${s.id}`)}
                className="cursor-pointer transition-colors hover:bg-zinc-50 dark:hover:bg-zinc-800/50"
              >
                <td className="px-4 py-3 font-mono text-xs">{s.code}</td>
                <td className="px-4 py-3 font-medium">{s.name}</td>
                <td className="px-4 py-3 text-zinc-600 dark:text-zinc-400">
                  {s.city || "—"}
                </td>
                <td className="px-4 py-3 text-zinc-600 dark:text-zinc-400">
                  {s.contact_person || "—"}
                </td>
                <td className="px-4 py-3 text-right">{s.default_lead_time_days} days</td>
                <td className="px-4 py-3 text-right">{s.product_count}</td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
