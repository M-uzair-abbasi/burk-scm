import type { ComponentProps } from "react";
import { Search } from "lucide-react";

import { cn } from "./cn";

const FIELD =
  "h-9 w-full rounded-md border border-strong bg-raised px-3 text-sm text-primary " +
  "placeholder:text-muted transition-colors duration-150 hover:border-accent/50 " +
  "disabled:opacity-50";

export function Input({ className, ...props }: ComponentProps<"input">) {
  return <input className={cn(FIELD, className)} {...props} />;
}

/** Search field with a leading icon — used on every list page's filter bar. */
export function SearchInput({ className, ...props }: ComponentProps<"input">) {
  return (
    <div className={cn("relative", className)}>
      <Search
        aria-hidden
        className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted"
      />
      <input type="search" className={cn(FIELD, "pl-9")} {...props} />
    </div>
  );
}
