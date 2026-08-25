"""Prove courier booking is fully automatic (Module 5): every shipped-or-later
order has exactly one Shipment with a real tracking number — no manual gap
between packing and booking. Same --check/CI contract as the other integrity
commands."""

from django.core.management.base import BaseCommand

from logistics.services import shipment_integrity


class Command(BaseCommand):
    help = "Verify every shipped order has an automatically-booked shipment."

    def add_arguments(self, parser):
        parser.add_argument("--check", action="store_true", help="Exit 1 on any breach.")

    def handle(self, *args, **options):
        report = shipment_integrity()
        if report["ok"]:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Shipment integrity OK. {report['total_shipments']} shipment(s), "
                    f"all automatically booked."
                )
            )
            return

        pending = set(report.get("pending_booking_orders", []))
        failed = set(report.get("failed_booking_orders", []))
        for ref in report["missing_shipment_orders"]:
            if ref in failed:
                detail = "booking job failed"
            elif ref in pending:
                detail = "booking job has not completed"
            else:
                detail = "no booking job exists"
            self.stdout.write(self.style.WARNING(f"{ref}: {detail}"))
        self.stdout.write(self.style.ERROR("Shipment integrity breach(es) found."))
        if options["check"]:
            raise SystemExit(1)
