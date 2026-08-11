"""Prove Synchronous Communication Latency (KPI #2).

Every packaging-video notification must have initiated (been sent, not just
scheduled) within 3 minutes of the order being sealed (session.completed_at).
Also reports shipment-tracking and review-request stats for visibility, though
only packaging_video carries the 3-minute contract. `--check` exits non-zero on
any breach, the same CI/demo gate as check_order_integrity / check_pack_integrity.
"""

from django.core.management.base import BaseCommand

from notifications.models import Notification
from notifications.services import latency_report


class Command(BaseCommand):
    help = "Verify every packaging-video notification dispatched within 3 minutes of sealing (KPI #2)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--check",
            action="store_true",
            help="Exit 1 on any breach without writing. Use in CI.",
        )

    def handle(self, *args, **options):
        video_report = latency_report(Notification.Kind.PACKAGING_VIDEO, threshold_seconds=180)

        for kind, label in Notification.Kind.choices:
            report = video_report if kind == Notification.Kind.PACKAGING_VIDEO else latency_report(kind)
            max_lat = report["max_latency_seconds"]
            max_lat_str = f"{max_lat:.1f}s" if max_lat is not None else "n/a"
            self.stdout.write(
                f"{label}: {report['sent']} sent (max latency {max_lat_str}), "
                f"{report['failed']} failed, {report['stuck']} stuck unscheduled."
            )

        if video_report["ok"]:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Dispatch latency OK. {video_report['sent']} packaging-video "
                    f"notification(s), all within 180s of sealing."
                )
            )
            return

        for n in video_report["breaches"]:
            self.stdout.write(
                self.style.WARNING(
                    f"BREACH: notification {n.id} ({n.order.reference}) took "
                    f"{n.latency_seconds:.1f}s (> 180s)"
                )
            )
        for n in video_report["stuck_detail"]:
            self.stdout.write(
                self.style.WARNING(
                    f"STUCK: notification {n.id} ({n.order.reference}) never scheduled or sent"
                )
            )
        self.stdout.write(self.style.ERROR("Dispatch latency breach(es) found."))
        if options["check"]:
            raise SystemExit(1)
