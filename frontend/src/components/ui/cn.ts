import clsx, { type ClassValue } from "clsx";

/**
 * Join class names. Deliberately thin — we don't pull in tailwind-merge
 * because the primitives below never accept classes that fight their own
 * base styles; callers extend (spacing, width), they don't override colour.
 */
export function cn(...inputs: ClassValue[]): string {
  return clsx(inputs);
}
