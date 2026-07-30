"""Prove the order queue has no dropped or duplicated records (KPI #3).

The KPI-3 analog of `recalculate_stock --check`. It independently re-fetches each
channel feed and verifies every fetched order is present in the queue (nothing
dropped) and that no (channel, external_id) pair has more than one row (nothing
duplicated). `--check` exits non-zero on any drift, for CI/demo gating.
"""

from django.core.management.base import BaseCommand

from orders.services import queue_integrity


class Command(BaseCommand):
    help = "Verify order-queue integrity: no dropped, no duplicated records (KPI #3)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--check",
            action="store_true",
            help="Exit 1 on any drift without writing. Use in CI.",
        )

    def handle(self, *args, **options):
        result = queue_integrity()

        for row in result["dropped_detail"]:
            self.stdout.write(
                self.style.WARNING(
                    f"DROPPED {row['channel']}:{row['external_id']} "
                    f"fetched but not in queue"
                )
            )
        for row in result["duplicated_detail"]:
            self.stdout.write(
                self.style.WARNING(
                    f"DUPLICATED {row['channel']}:{row['external_id']} "
                    f"appears {row['count']} times"
                )
            )

        if result["ok"]:
            self.stdout.write(
                self.style.SUCCESS(
                    f"0 dropped, 0 duplicated, {result['unique']} unique orders. "
                    f"Queue integrity OK."
                )
            )
            return

        self.stdout.write(
            self.style.ERROR(
                f"{result['dropped']} dropped, {result['duplicated']} duplicated, "
                f"{result['unique']} unique orders."
            )
        )
        if options["check"]:
            raise SystemExit(1)
