"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Bell, ScanLine, ShoppingCart, Truck } from "lucide-react";

import { useAuth } from "@/components/AuthProvider";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { ApiError } from "@/lib/api";

const LOOP = [
  { icon: ShoppingCart, label: "Orders arrive" },
  { icon: ScanLine, label: "Items verified" },
  { icon: Bell, label: "Customer notified" },
  { icon: Truck, label: "Courier booked" },
];

export default function LoginPage() {
  const { user, loading, login } = useAuth();
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // Already signed in? Skip the form.
  useEffect(() => {
    if (!loading && user) router.replace("/dashboard");
  }, [loading, user, router]);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(username, password);
      router.replace("/dashboard");
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Something went wrong. Try again.",
      );
      setSubmitting(false);
    }
  }

  /** Fills the form for a demo account — evaluators should not have to type. */
  function fillDemo(name: string) {
    setUsername(name);
    setPassword("burkdemo123");
    setError(null);
  }

  return (
    <div className="flex min-h-screen flex-col lg:flex-row">
      {/* Explainer half — so someone meeting this system cold knows what it is
          before they are asked for credentials. */}
      <section className="flex flex-col justify-center gap-8 bg-instrument px-8 py-12 text-instrument-text lg:w-[46%] lg:px-14">
        <div className="flex items-center gap-2.5">
          <span
            aria-hidden
            className="flex size-8 items-center justify-center rounded-md bg-instrument-raised text-xs font-bold"
          >
            BK
          </span>
          <div className="leading-tight">
            <div className="text-sm font-semibold">Burk.pk SCM-OVS</div>
            <div className="eyebrow text-instrument-muted">
              Warehouse console
            </div>
          </div>
        </div>

        <div>
          <h1 className="text-2xl font-semibold leading-tight tracking-tight lg:text-3xl">
            Supply chain &amp; smart order verification
          </h1>
          <p className="mt-3 max-w-md text-sm leading-relaxed text-instrument-muted">
            One loop, start to finish: orders are pulled from every sales
            channel, each item is barcode-checked as it is packed, and the
            sealed parcel is filmed, the customer messaged and a courier booked
            without anyone typing an airway bill.
          </p>
        </div>

        <ul className="flex flex-col gap-3">
          {LOOP.map((step, i) => {
            const Icon = step.icon;
            return (
              <li key={step.label} className="flex items-center gap-3">
                <span className="flex size-7 shrink-0 items-center justify-center rounded-full border border-instrument-border text-instrument-muted">
                  <Icon aria-hidden className="size-3.5" />
                </span>
                <span className="text-sm text-instrument-text">
                  {step.label}
                </span>
                {i < LOOP.length - 1 ? (
                  <span aria-hidden className="text-instrument-border">
                    →
                  </span>
                ) : null}
              </li>
            );
          })}
        </ul>
      </section>

      {/* Form half */}
      <section className="flex flex-1 items-center justify-center px-6 py-12">
        <div className="w-full max-w-sm">
          <h2 className="text-lg font-semibold tracking-tight text-primary">
            Sign in
          </h2>
          <p className="mt-1 text-sm text-secondary">
            Use a warehouse account to open the console.
          </p>

          <form onSubmit={onSubmit} className="mt-6 flex flex-col gap-4">
            {error ? (
              <div
                role="alert"
                className="rounded-lg border border-critical/30 bg-critical-soft px-3 py-2 text-sm text-critical-text"
              >
                {error}
              </div>
            ) : null}

            <div>
              <label
                htmlFor="username"
                className="eyebrow mb-1.5 block text-muted"
              >
                Username
              </label>
              <Input
                id="username"
                type="text"
                autoComplete="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required
              />
            </div>

            <div>
              <label
                htmlFor="password"
                className="eyebrow mb-1.5 block text-muted"
              >
                Password
              </label>
              <Input
                id="password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </div>

            <Button
              type="submit"
              variant="primary"
              size="lg"
              disabled={submitting}
              className="w-full"
            >
              {submitting ? "Signing in…" : "Sign in"}
            </Button>
          </form>

          <div className="mt-8 rounded-lg border border-subtle bg-raised p-4">
            <div className="eyebrow text-muted">Demo accounts</div>
            <p className="mt-1.5 text-xs leading-relaxed text-secondary">
              Pick one to fill the form. A manager sees everything; an operator
              sees packing and stock.
            </p>
            <div className="mt-3 flex gap-2">
              <Button size="sm" variant="secondary" onClick={() => fillDemo("manager")}>
                manager
              </Button>
              <Button size="sm" variant="secondary" onClick={() => fillDemo("operator")}>
                operator
              </Button>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
