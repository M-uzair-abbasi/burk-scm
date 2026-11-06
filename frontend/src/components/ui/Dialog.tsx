"use client";

import * as RD from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "./cn";

/**
 * Modal built on Radix so focus trapping, escape-to-close, scroll locking and
 * the labelling relationships are correct without hand-rolling them.
 */
export function Dialog({
  open,
  onOpenChange,
  title,
  description,
  children,
  footer,
  className,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: string;
  children: ReactNode;
  footer?: ReactNode;
  className?: string;
}) {
  return (
    <RD.Root open={open} onOpenChange={onOpenChange}>
      <RD.Portal>
        <RD.Overlay className="fixed inset-0 z-40 bg-instrument/55 backdrop-blur-[2px]" />
        <RD.Content
          className={cn(
            "fixed left-1/2 top-1/2 z-50 w-[calc(100vw-2rem)] max-w-md -translate-x-1/2 -translate-y-1/2",
            "rounded-xl border border-subtle bg-raised shadow-overlay focus:outline-none",
            className,
          )}
        >
          <div className="flex items-start justify-between gap-4 border-b border-subtle px-5 py-3.5">
            <div className="min-w-0">
              <RD.Title className="text-sm font-semibold text-primary">
                {title}
              </RD.Title>
              {description ? (
                <RD.Description className="mt-1 text-xs leading-relaxed text-secondary">
                  {description}
                </RD.Description>
              ) : null}
            </div>
            <RD.Close
              aria-label="Close"
              className="-m-1 rounded-md p-1 text-muted transition-colors duration-150 hover:bg-hover hover:text-primary"
            >
              <X className="size-4" />
            </RD.Close>
          </div>

          <div className="px-5 py-4">{children}</div>

          {footer ? (
            <div className="flex items-center justify-end gap-2 border-t border-subtle px-5 py-3.5">
              {footer}
            </div>
          ) : null}
        </RD.Content>
      </RD.Portal>
    </RD.Root>
  );
}

export const DialogClose = RD.Close;
