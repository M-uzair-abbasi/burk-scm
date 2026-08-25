import time

from django.core.management.base import BaseCommand

from operations.models import WorkItem
from operations.services import process_due


class Command(BaseCommand):
    help = "Continuously process durable work; use --once for one bounded batch."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="Process one batch.")
        parser.add_argument("--limit", type=int, default=25)
        parser.add_argument("--worker-name", default="management-command")
        parser.add_argument("--poll-interval", type=float, default=1.0)

    def handle(self, *args, **options):
        try:
            while True:
                claimed = self._run_batch(options)
                if options["once"]:
                    return
                if not claimed:
                    time.sleep(max(0.1, options["poll_interval"]))
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("Worker stopped."))

    def _run_batch(self, options):
        claimed = process_due(
            limit=max(0, options["limit"]), worker_name=options["worker_name"]
        )
        counts = {status: 0 for status in WorkItem.Status.values}
        for item in WorkItem.objects.filter(pk__in=[row.pk for row in claimed]):
            counts[item.status] += 1
        if claimed or options["once"]:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Claimed {len(claimed)} work item(s): "
                    f"{counts[WorkItem.Status.SUCCEEDED]} succeeded, "
                    f"{counts[WorkItem.Status.RETRY]} retrying, "
                    f"{counts[WorkItem.Status.FAILED]} failed."
                )
            )
        return claimed
