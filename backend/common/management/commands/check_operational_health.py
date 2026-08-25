import json

from django.core.management.base import BaseCommand

from common.health import operational_health


class Command(BaseCommand):
    help = "Check database, worker, backlog, media, and adapter readiness."

    def add_arguments(self, parser):
        parser.add_argument("--check", action="store_true", help="Exit 1 if unhealthy.")

    def handle(self, *args, **options):
        report = operational_health()
        self.stdout.write(json.dumps(report, default=str, indent=2))
        if report["ok"]:
            self.stdout.write(self.style.SUCCESS("Operational health OK."))
        else:
            self.stdout.write(self.style.ERROR("Operational health is degraded."))
            if options["check"]:
                raise SystemExit(1)
