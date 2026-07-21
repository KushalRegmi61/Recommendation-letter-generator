"""Delete auto-generated '(copy)' template rows left behind by repeated
Duplicate clicks. Owned templates only; system templates are never touched.

Dry run by default; pass --commit to actually delete.
"""
import re

from django.core.management.base import BaseCommand

from home.models import CustomTemplates

# Matches names ending in " (copy)" or " (copy) 7", the exact shapes
# duplicate_template produces.
COPY_RE = re.compile(r" \(copy\)( \d+)?$")


class Command(BaseCommand):
    help = "Prune owned '(copy)' template duplicates. Dry run unless --commit."

    def add_arguments(self, parser):
        parser.add_argument(
            "--commit",
            action="store_true",
            help="Actually delete the rows (default: dry run).",
        )

    def handle(self, *args, **options):
        owned = CustomTemplates.objects.filter(professor__isnull=False)
        victims = [
            t for t in owned
            if t.template_name and COPY_RE.search(t.template_name)
        ]
        for t in victims:
            verb = "DELETE" if options["commit"] else "would delete"
            self.stdout.write(f"{verb}: [prof {t.professor_id}] {t.template_name}")

        if options["commit"]:
            count = CustomTemplates.objects.filter(
                pk__in=[t.pk for t in victims]
            ).delete()[0]
            self.stdout.write(self.style.SUCCESS(f"Deleted {count} copy templates."))
        else:
            self.stdout.write(
                f"Dry run: {len(victims)} rows would be deleted. Re-run with --commit."
            )
