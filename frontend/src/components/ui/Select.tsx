"use client";

import * as RS from "@radix-ui/react-select";
import { Check, ChevronDown } from "lucide-react";

import { cn } from "./cn";

export interface SelectOption {
  value: string;
  label: string;
}

/**
 * Replaces the raw native <select> the old filter bars used. A native control
 * cannot be styled to match the rest of the field row on every platform, so
 * the filters looked pasted-in; this one matches `Input` exactly.
 *
 * Radix requires a non-empty value per item, so "no filter" is represented by
 * the sentinel ALL rather than an empty string.
 */
export const ALL = "__all__";

export function Select({
  value,
  onValueChange,
  options,
  placeholder = "Select…",
  className,
  ariaLabel,
}: {
  value: string;
  onValueChange: (value: string) => void;
  options: SelectOption[];
  placeholder?: string;
  className?: string;
  ariaLabel?: string;
}) {
  return (
    <RS.Root value={value} onValueChange={onValueChange}>
      <RS.Trigger
        aria-label={ariaLabel}
        className={cn(
          "inline-flex h-9 items-center justify-between gap-2 rounded-md border border-strong",
          "bg-raised px-3 text-sm text-primary transition-colors duration-150",
          "hover:border-accent/50 data-[placeholder]:text-muted",
          className,
        )}
      >
        <RS.Value placeholder={placeholder} />
        <RS.Icon>
          <ChevronDown className="size-4 text-muted" />
        </RS.Icon>
      </RS.Trigger>

      <RS.Portal>
        <RS.Content
          position="popper"
          sideOffset={4}
          className="z-50 overflow-hidden rounded-lg border border-subtle bg-raised shadow-overlay"
        >
          <RS.Viewport className="p-1">
            {options.map((option) => (
              <RS.Item
                key={option.value}
                value={option.value}
                className={cn(
                  "relative flex cursor-pointer select-none items-center gap-2 rounded-md py-1.5 pl-7 pr-3",
                  "text-sm text-primary outline-none",
                  "data-[highlighted]:bg-hover data-[state=checked]:font-medium",
                )}
              >
                <RS.ItemIndicator className="absolute left-2 inline-flex">
                  <Check className="size-3.5 text-accent" />
                </RS.ItemIndicator>
                <RS.ItemText>{option.label}</RS.ItemText>
              </RS.Item>
            ))}
          </RS.Viewport>
        </RS.Content>
      </RS.Portal>
    </RS.Root>
  );
}
