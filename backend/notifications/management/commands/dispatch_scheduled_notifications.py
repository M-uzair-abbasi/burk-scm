"""Send any notification whose scheduled_for has come due.

Stands in for a real cron / Celery-beat tick — the same "manual trigger acts as
the scheduler" pattern sync_orders uses for channel polling. In production this
would run every few minutes; here it's run on demand for the demo (e.g. the
Module 6 review reminder, scheduled a short delay after delivery).
"""

from django.core.management.base import BaseCommand

from notifications.services import dispatch_due_scheduled


class Command(BaseCommand):
    help = "Send every SCHEDULED notification whose scheduled_for time has passed."

    def handle(self, *args, **options):
        sent = dispatch_due_scheduled()
        if not sent:
            self.stdout.write("No due notifications.")
            return
        for n in sent:
            self.stdout.write(
                f"{n.get_kind_display()} -> {n.recipient} via {n.channel}: {n.get_status_display()}"
            )
        self.stdout.write(self.style.SUCCESS(f"Dispatched {len(sent)} notification(s)."))
