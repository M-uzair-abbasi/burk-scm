import type { Product } from "@/lib/types";

type StockLike = Pick<Product, "quantity_on_hand" | "is_low_stock">;

/** Green "In stock" / amber "Low" / red "Out of stock" derived from the row. */
export function StockStatusPill({ product }: { product: StockLike }) {
  let label: string;
  let cls: string;

  if (product.quantity_on_hand <= 0) {
    label = "Out of stock";
    cls = "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300";
  } else if (product.is_low_stock) {
    label = "Low";
    cls = "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300";
  } else {
    label = "In stock";
    cls = "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300";
  }

  return (
    <span
      className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${cls}`}
    >
      {label}
    </span>
  );
}
