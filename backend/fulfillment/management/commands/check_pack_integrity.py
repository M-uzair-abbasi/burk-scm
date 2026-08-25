"""Prove barcode-verification integrity (KPI #1).

Asserts that (a) no COMPLETED packing session has an unfinished line, and (b) no
mismatch scan was ever counted as packing progress (a mismatch must carry no
line). `--check` exits non-zero on any breach, for CI/demo gating — the KPI-1
analog of `check_order_integrity` / `recalculate_stock --check`.
"""

from django.core.management.base import BaseCommand

from fulfillment.models import PackingSession, PackScan
from fulfillment.services import session_progress


class Command(BaseCommand):
    help = "Verify packing integrity: completed packs fully scanned, no mismatch packed (KPI #1)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--check",
            action="store_true",
            help="Exit 1 on any breach without writing. Use in CI.",
        )

    def handle(self, *args, **options):
        breaches = []
        qualifying_sessions = 0

        # (a) every completed session's lines are fully scanned by ok scans
        for session in PackingSession.objects.filter(
            status=PackingSession.Status.COMPLETED
        ):
            prog = session_progress(session)
            if not prog["lines"]:
                breaches.append(f"session {session.id}: completed with no order lines")
                continue
            qualifying_sessions += 1
            invalid_quantities = [
                f"{p['line'].product_name} ({p['required']})"
                for p in prog["lines"]
                if p["required"] <= 0
            ]
            if invalid_quantities:
                breaches.append(
                    f"session {session.id}: non-positive quantities {invalid_quantities}"
                )
            if not prog["complete"]:
                unfinished = [
                    f"{p['line'].product_name} {p['scanned']}/{p['required']}"
                    for p in prog["lines"]
                    if not p["complete"]
                ]
                breaches.append(f"session {session.id}: unfinished lines {unfinished}")

        if qualifying_sessions == 0:
            breaches.append("no completed non-empty packing session evidence")

        # (b) a mismatch scan must never be attached to a line (never counts)
        bad = PackScan.objects.filter(
            result=PackScan.Result.MISMATCH, line__isnull=False
        ).count()
        if bad:
            breaches.append(f"{bad} mismatch scan(s) wrongly attached to a line")

        total = PackScan.objects.count()
        mismatches = PackScan.objects.filter(result=PackScan.Result.MISMATCH).count()

        for b in breaches:
            self.stdout.write(self.style.WARNING(b))

        if not breaches:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Packing integrity OK. {total} scan(s) logged, "
                    f"{mismatches} mismatch(es) all intercepted, 0 counted as packed; "
                    f"{qualifying_sessions} completed pack(s) verified."
                )
            )
            return

        self.stdout.write(self.style.ERROR(f"{len(breaches)} integrity breach(es)."))
        if options["check"]:
            raise SystemExit(1)
