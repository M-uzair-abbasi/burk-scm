import Link from "next/link";
import type { ComponentProps, ReactNode } from "react";

import { cn } from "./cn";

type Variant = "primary" | "secondary" | "ghost" | "danger" | "instrument";
type Size = "sm" | "md" | "lg";

const VARIANTS: Record<Variant, string> = {
  // Accent is reserved for interaction — this is the only place it carries
  // a filled background on a work surface.
  primary:
    "bg-accent text-accent-on hover:bg-accent-hover border border-transparent shadow-card",
  secondary:
    "bg-raised text-primary border border-strong hover:bg-hover",
  ghost:
    "bg-transparent text-secondary border border-transparent hover:bg-hover hover:text-primary",
  danger:
    "bg-critical text-white border border-transparent hover:opacity-90",
  // For use inside dark instrument panels.
  instrument:
    "bg-instrument-raised text-instrument-text border border-instrument-border hover:border-accent-bright/60",
};

const SIZES: Record<Size, string> = {
  sm: "h-8 px-3 text-[13px] gap-1.5 rounded-md",
  md: "h-9 px-3.5 text-sm gap-2 rounded-md",
  lg: "h-11 px-5 text-base gap-2 rounded-lg",
};

const BASE =
  "inline-flex items-center justify-center font-medium transition-colors duration-150 " +
  "disabled:opacity-50 disabled:pointer-events-none select-none whitespace-nowrap";

interface CommonProps {
  variant?: Variant;
  size?: Size;
  className?: string;
  children?: ReactNode;
}

export function Button({
  variant = "secondary",
  size = "md",
  className,
  ...props
}: CommonProps & ComponentProps<"button">) {
  return (
    <button
      className={cn(BASE, VARIANTS[variant], SIZES[size], className)}
      {...props}
    />
  );
}

/** Same visual language, but renders an anchor — for navigation, not actions. */
export function ButtonLink({
  variant = "secondary",
  size = "md",
  className,
  ...props
}: CommonProps & ComponentProps<typeof Link>) {
  return (
    <Link
      className={cn(BASE, VARIANTS[variant], SIZES[size], className)}
      {...props}
    />
  );
}
