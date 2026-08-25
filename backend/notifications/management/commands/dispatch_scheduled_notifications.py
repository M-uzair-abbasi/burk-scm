"""Drain one batch of due notification jobs through the durable worker."""

from django.core.management.base import BaseCommand

from notifications.services import dispatch_due_scheduled


class Command(BaseCommand):
    help = "Process one batch of due notification outbox jobs."

    def handle(self, *args, **options):
        processed = dispatch_due_scheduled()
        if not processed:
            self.stdout.write("No due notifications.")
            return
        for n in processed:
            self.stdout.write(
                f"{n.get_kind_display()} -> {n.recipient} via {n.channel}: {n.get_status_display()}"
            )
        self.stdout.write(
            self.style.SUCCESS(f"Processed {len(processed)} notification job(s).")
        )
