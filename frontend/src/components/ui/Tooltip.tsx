"use client";

import * as RT from "@radix-ui/react-tooltip";
import type { ReactNode } from "react";

import { cn } from "./cn";

export function TooltipProvider({ children }: { children: ReactNode }) {
  return (
    <RT.Provider delayDuration={200} skipDelayDuration={300}>
      {children}
    </RT.Provider>
  );
}

const CONTENT =
  "z-50 max-w-xs rounded-lg border border-instrument-border bg-instrument px-3 py-2 " +
  "text-xs leading-relaxed text-instrument-text shadow-overlay";

export function Tooltip({
  content,
  children,
  side = "top",
}: {
  content: ReactNode;
  children: ReactNode;
  side?: "top" | "right" | "bottom" | "left";
}) {
  return (
    <RT.Root>
      <RT.Trigger asChild>{children}</RT.Trigger>
      <RT.Portal>
        <RT.Content side={side} sideOffset={6} className={CONTENT}>
          {content}
          <RT.Arrow className="fill-instrument" />
        </RT.Content>
      </RT.Portal>
    </RT.Root>
  );
}

/**
 * A domain term a newcomer will not know — "safety stock", "source lag",
 * "airway bill". Renders with a dotted underline so it advertises that an
 * explanation is available, and stays keyboard reachable.
 */
export function Term({
  children,
  definition,
  className,
}: {
  children: ReactNode;
  definition: ReactNode;
  className?: string;
}) {
  return (
    <Tooltip content={definition}>
      <button
        type="button"
        className={cn(
          "cursor-help underline decoration-dotted decoration-from-font underline-offset-4",
          "text-inherit transition-colors duration-150 hover:text-accent-text",
          className,
        )}
      >
        {children}
      </button>
    </Tooltip>
  );
}
