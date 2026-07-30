"""Pull every channel feed into the unified order queue (CLI equivalent of "Sync now")."""

from django.core.management.base import BaseCommand

from orders.services import sync_all


class Command(BaseCommand):
    help = "Pull all channel feeds into the unified order queue."

    def handle(self, *args, **options):
        runs = sync_all()
        for run in runs:
            style = self.style.SUCCESS if run.reconciled and run.ok else self.style.ERROR
            self.stdout.write(
                style(
                    f"{run.channel:6} fetched={run.fetched} created={run.created} "
                    f"updated={run.updated} dup_skipped={run.duplicates_skipped} "
                    f"failed={run.failed} reconciled={run.reconciled}"
                )
            )
        self.stdout.write(self.style.SUCCESS("Sync complete."))
