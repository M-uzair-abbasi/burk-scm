import json

from django.core.management.base import BaseCommand

from common.metrics import operational_metrics


class Command(BaseCommand):
    help = "Check bounded operational aggregates against configured thresholds."

    def add_arguments(self, parser):
        parser.add_argument("--check", action="store_true", help="Exit 1 on breach.")

    def handle(self, *args, **options):
        report = operational_metrics()
        self.stdout.write(json.dumps(report, default=str, indent=2))
        if report["ok"]:
            self.stdout.write(self.style.SUCCESS("Operational metrics OK."))
        else:
            self.stdout.write(self.style.ERROR("Operational metric breach(es) found."))
            if options["check"]:
                raise SystemExit(1)
