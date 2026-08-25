from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from operations.models import WorkerHeartbeat


class Command(BaseCommand):
    help = "Exit non-zero unless the named durable worker heartbeat is fresh."

    def add_arguments(self, parser):
        parser.add_argument("--worker-name", required=True)
        parser.add_argument(
            "--max-age",
            type=float,
            default=settings.WORKER_HEARTBEAT_MAX_AGE_SECONDS,
        )

    def handle(self, *args, **options):
        name = options["worker_name"]
        max_age = max(0.0, options["max_age"])
        heartbeat = WorkerHeartbeat.objects.filter(name=name).first()
        if heartbeat is None:
            raise CommandError(f"Worker heartbeat {name!r} does not exist.")
        age = max(0.0, (timezone.now() - heartbeat.last_seen_at).total_seconds())
        if age > max_age:
            raise CommandError(
                f"Worker heartbeat {name!r} is stale ({age:.1f}s > {max_age:.1f}s)."
            )
        self.stdout.write(self.style.SUCCESS(f"Worker {name!r} healthy ({age:.1f}s)."))
