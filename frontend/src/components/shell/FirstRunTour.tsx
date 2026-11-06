"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import {
  Boxes,
  ClipboardList,
  LayoutDashboard,
  ScanLine,
  ShoppingCart,
  X,
  type LucideIcon,
} from "lucide-react";

import { Button } from "@/components/ui/Button";
import { cn } from "@/components/ui/cn";

const STORAGE_KEY = "burk.tour.v1.done";
/** Any component can re-open the tour by dispatching this on window. */
export const START_TOUR_EVENT = "burk:start-tour";

interface Step {
  path: string;
  icon: LucideIcon;
  title: string;
  body: string;
  managerOnly?: boolean;
}

/**
 * The tour actually walks the console: each step navigates to the screen it
 * describes and the card stays out of the way at the bottom of the viewport,
 * so you read the explanation while looking at the real thing. A modal that
 * covered the page would teach nothing.
 */
const STEPS: Step[] = [
  {
    path: "/dashboard",
    icon: LayoutDashboard,
    title: "Start here every shift",
    body: "The card at the top names the single most useful thing to do right now — usually the next order to pack. Below it, the pipeline shows where every order currently sits.",
  },
  {
    path: "/packing",
    icon: ScanLine,
    title: "The packing station",
    body: "Open an order and scan each item. If something does not belong to that order the screen flashes red and refuses it, so a wrong item cannot reach a customer. Sealing then films the parcel, messages the customer and books a courier on its own.",
  },
  {
    path: "/orders",
    icon: ShoppingCart,
    title: "Every order, reconciled",
    body: "Orders are pulled from Burk.pk and Daraz.pk automatically. The dark strip proves nothing was dropped, duplicated or silently changed at the source — those counters must read zero.",
  },
  {
    path: "/inventory",
    icon: Boxes,
    title: "Stock that maintains itself",
    body: "Packing decrements stock and receiving a purchase order restores it, so counts stay honest. Anything at or below its safety level is flagged for reorder.",
  },
  {
    path: "/purchase-orders",
    icon: ClipboardList,
    title: "Restocking",
    body: "Reordering a low-stock product raises a draft purchase order here, priced from the preferred supplier's tiers. Receiving it puts the stock straight back on the shelf.",
    managerOnly: true,
  },
];

function markDone() {
  try {
    window.localStorage.setItem(STORAGE_KEY, "1");
  } catch {
    // Private mode or blocked storage — the tour simply shows again next time.
  }
}

function alreadyDone(): boolean {
  try {
    return window.localStorage.getItem(STORAGE_KEY) === "1";
  } catch {
    return false;
  }
}

export function FirstRunTour({ isManager }: { isManager: boolean }) {
  const router = useRouter();
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const [index, setIndex] = useState(0);

  const steps = STEPS.filter((s) => !s.managerOnly || isManager);

  useEffect(() => {
    let alive = true;

    // Deferred by a microtask on purpose: localStorage is unavailable during
    // server rendering, so reading it must happen after hydration rather than
    // synchronously inside this effect.
    Promise.resolve().then(() => {
      if (alive && !alreadyDone()) setOpen(true);
    });

    function onStart() {
      setIndex(0);
      setOpen(true);
    }
    window.addEventListener(START_TOUR_EVENT, onStart);
    return () => {
      alive = false;
      window.removeEventListener(START_TOUR_EVENT, onStart);
    };
  }, []);

  if (!open || steps.length === 0) return null;

  const step = steps[Math.min(index, steps.length - 1)];
  const isLast = index >= steps.length - 1;
  const Icon = step.icon;

  function go(nextIndex: number) {
    const next = steps[nextIndex];
    setIndex(nextIndex);
    if (next && next.path !== pathname) router.push(next.path);
  }

  function finish() {
    markDone();
    setOpen(false);
  }

  return (
    <div
      role="dialog"
      aria-label="Getting started tour"
      className="fixed inset-x-4 bottom-4 z-40 mx-auto max-w-md rounded-xl border border-instrument-border bg-instrument p-5 text-instrument-text shadow-overlay sm:inset-x-auto sm:right-6 sm:mx-0"
    >
      <div className="flex items-start gap-3">
        <span className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-full bg-instrument-raised text-accent-bright">
          <Icon aria-hidden className="size-4" />
        </span>
        <div className="min-w-0 flex-1">
          <div className="eyebrow text-instrument-muted">
            Getting started · {index + 1} of {steps.length}
          </div>
          <h2 className="mt-1.5 text-sm font-semibold">{step.title}</h2>
          <p className="mt-1.5 text-xs leading-relaxed text-instrument-muted">
            {step.body}
          </p>
        </div>
        <button
          onClick={finish}
          aria-label="Skip tour"
          className="-m-1 rounded-md p-1 text-instrument-muted transition-colors duration-150 hover:bg-instrument-raised hover:text-instrument-text"
        >
          <X className="size-4" />
        </button>
      </div>

      <div className="mt-4 flex items-center justify-between gap-3">
        <div className="flex gap-1.5" aria-hidden>
          {steps.map((s, i) => (
            <span
              key={s.path}
              className={cn(
                "h-1 rounded-full transition-all duration-200",
                i === index
                  ? "w-5 bg-accent-bright"
                  : "w-1.5 bg-instrument-border",
              )}
            />
          ))}
        </div>

        <div className="flex items-center gap-2">
          <Button size="sm" variant="instrument" onClick={finish}>
            Skip
          </Button>
          {index > 0 ? (
            <Button
              size="sm"
              variant="instrument"
              onClick={() => go(index - 1)}
            >
              Back
            </Button>
          ) : null}
          <Button
            size="sm"
            variant="primary"
            onClick={() => (isLast ? finish() : go(index + 1))}
          >
            {isLast ? "Finish" : "Next"}
          </Button>
        </div>
      </div>
    </div>
  );
}
