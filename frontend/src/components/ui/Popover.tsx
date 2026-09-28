"use client";

import * as RP from "@radix-ui/react-popover";
import type { ReactNode } from "react";

import { cn } from "./cn";

/**
 * Anchored panel. Used by the first-run tour to point at a real element on
 * the page rather than describing it in the abstract.
 */
export function Popover({
  open,
  onOpenChange,
  anchor,
  children,
  side = "bottom",
  align = "start",
  className,
}: {
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  anchor: ReactNode;
  children: ReactNode;
  side?: "top" | "right" | "bottom" | "left";
  align?: "start" | "center" | "end";
  className?: string;
}) {
  return (
    <RP.Root open={open} onOpenChange={onOpenChange}>
      <RP.Trigger asChild>{anchor}</RP.Trigger>
      <RP.Portal>
        <RP.Content
          side={side}
          align={align}
          sideOffset={10}
          collisionPadding={16}
          className={cn(
            "z-50 w-80 rounded-xl border border-instrument-border bg-instrument p-4",
            "text-instrument-text shadow-overlay focus:outline-none",
            className,
          )}
        >
          {children}
          <RP.Arrow className="fill-instrument" width={12} height={6} />
        </RP.Content>
      </RP.Portal>
    </RP.Root>
  );
}

export const PopoverAnchor = RP.Anchor;
