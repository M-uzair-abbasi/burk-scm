from django.core.management.base import BaseCommand

from surveillance.services import cleanup_packaging_media


class Command(BaseCommand):
    help = "Delete packaging media past retention while retaining audit rows."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true", help="Report without deleting files."
        )
        parser.add_argument(
            "--check",
            action="store_true",
            help="Exit 1 if deletion backlog, unsafe paths, or invalid policy exists.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"] or options["check"]
        report = cleanup_packaging_media(dry_run=dry_run)
        self.stdout.write(
            f"Raw due: {report['raw_due']}; compressed due: "
            f"{report['compressed_due']}; deleted: {report['deleted']}; "
            f"already missing: {report['missing']}; unsafe: {report['unsafe']}."
        )
        for error in report["configuration_errors"]:
            self.stdout.write(self.style.WARNING(f"CONFIG: {error}"))
        unhealthy = bool(
            report["pending"]
            or report["unsafe"]
            or report["configuration_errors"]
        )
        if options["check"] and unhealthy:
            raise SystemExit(1)
        if unhealthy and dry_run:
            self.stdout.write(self.style.WARNING("Packaging-media cleanup is due."))
        elif report["unsafe"] or report["configuration_errors"]:
            self.stdout.write(
                self.style.WARNING("Cleanup completed with unresolved policy errors.")
            )
        else:
            self.stdout.write(self.style.SUCCESS("Packaging-media retention is clean."))
