import re

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from main.models import PropertyOwnerIntake


RANDOMISH_RE = re.compile(r"^[a-z]{8,14}$", re.IGNORECASE)
SUSPICIOUS_EMAIL_DOMAINS = {
    "bellff.com",
    "bellsbeer.com",
    "deepmails.org",
    "gongjua.com",
    "immenseignite.info",
    "rulersonline.com",
}


def email_domain(email):
    value = (email or "").strip().lower()
    if "@" not in value:
        return ""
    return value.rsplit("@", 1)[1]


def randomish(value):
    return bool(RANDOMISH_RE.match((value or "").strip()))


def text_without_spaces(value):
    return re.sub(r"\s+", "", value or "")


def spam_reasons(intake):
    reasons = []
    if intake.property_count >= 1000 or intake.total_units >= 1000:
        reasons.append("implausibly large portfolio counts")
    if randomish(intake.full_name) and randomish(intake.company_name):
        reasons.append("random-looking name and company")
    if email_domain(intake.email) in SUSPICIOUS_EMAIL_DOMAINS:
        reasons.append("known junk email domain")

    long_text_fields = [
        intake.current_pain_points,
        intake.migration_notes,
        intake.dashboard_goals,
        intake.additional_notes,
    ]
    if any(len(text_without_spaces(value)) >= 24 and randomish(text_without_spaces(value)[:12]) for value in long_text_fields):
        reasons.append("random-looking long text")

    if len(reasons) >= 2:
        return reasons
    return []


class Command(BaseCommand):
    help = "Preview, close, or delete spammy RentalReadyPro owner setup questionnaires."

    def add_arguments(self, parser):
        parser.add_argument("--confirm", action="store_true", help="Required to modify records.")
        parser.add_argument("--delete", action="store_true", help="Delete suspect records instead of marking them closed lost.")
        parser.add_argument("--limit", type=int, default=100, help="Maximum suspect records to show or process.")

    def handle(self, *args, **options):
        suspects = []
        for intake in PropertyOwnerIntake.objects.all().order_by("-created_at")[:1000]:
            reasons = spam_reasons(intake)
            if reasons:
                suspects.append((intake, reasons))
            if len(suspects) >= options["limit"]:
                break

        self.stdout.write("Spam owner intake cleanup preview")
        self.stdout.write("=================================")
        self.stdout.write(f"Suspect intakes: {len(suspects)}")
        for intake, reasons in suspects:
            self.stdout.write(
                f"{intake.id} | {intake.full_name} | {intake.company_name or '-'} | "
                f"{intake.email} | properties={intake.property_count} | units={intake.total_units} | "
                f"{intake.created_at:%Y-%m-%d %H:%M} | {', '.join(reasons)}"
            )

        if not suspects:
            return

        if not options["confirm"]:
            self.stdout.write("")
            self.stdout.write("Dry run only. No records were changed.")
            if options["delete"]:
                self.stdout.write("Run again with --delete --confirm to delete these records.")
            else:
                self.stdout.write("Run again with --confirm to mark them closed lost with a spam cleanup note.")
            return

        with transaction.atomic():
            if options["delete"]:
                ids = [intake.id for intake, _reasons in suspects]
                deleted = PropertyOwnerIntake.objects.filter(id__in=ids).delete()[0]
                self.stdout.write("")
                self.stdout.write(self.style.SUCCESS(f"Deleted suspect owner intakes: {deleted}"))
                return

            now = timezone.now()
            updated = 0
            for intake, reasons in suspects:
                note = f"[{now:%Y-%m-%d %H:%M}] Spam cleanup: {', '.join(reasons)}"
                intake.lead_stage = "closed_lost"
                intake.internal_notes = f"{intake.internal_notes}\n{note}".strip()
                intake.save(update_fields=["lead_stage", "internal_notes"])
                updated += 1

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"Marked suspect owner intakes closed lost: {updated}"))
