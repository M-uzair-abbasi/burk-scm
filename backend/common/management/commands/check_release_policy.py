from django.core.management.base import BaseCommand, CommandError

from common.release import release_configuration_violations


class Command(BaseCommand):
    help = "Reject unsafe, demo, simulated, or placeholder live-release settings."

    def handle(self, *args, **options):
        violations = release_configuration_violations()
        if violations:
            for violation in violations:
                self.stdout.write(self.style.ERROR(f"BLOCKED: {violation}"))
            raise CommandError(f"Release policy found {len(violations)} violation(s).")
        self.stdout.write(self.style.SUCCESS("Release configuration policy OK."))
