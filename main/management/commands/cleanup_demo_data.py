from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q

from main.models import (
    AccountingReceipt,
    FinancialEntry,
    FinancialUpload,
    HousingApplication,
    Property,
    PropertyOwnerIntake,
    User,
)


DEMO_PROPERTY_NAMES = [
    "Demo Ridge Apartments",
    "Cedar Market Lofts",
    "Pine Street Villas",
    "Harbor View Senior Living",
]

DEMO_USERNAMES = [
    "demo-admin",
    "demo-owner-olivia",
    "demo-owner-marcus",
    "demo-landlord-larry",
    "demo-landlord-nina",
]

DEMO_OWNER_LEAD_EMAILS = [
    "owner-lead@example.com",
    "carter-assets@example.com",
    "stonebridge@example.com",
    "harbor-portfolio@example.com",
]


class Command(BaseCommand):
    help = "Remove seeded RentalReadyPro demo data from a non-demo database."

    def add_arguments(self, parser):
        parser.add_argument("--confirm", action="store_true", help="Required to delete demo data.")

    def handle(self, *args, **options):
        demo_properties = Property.objects.filter(name__in=DEMO_PROPERTY_NAMES)
        demo_uploads = FinancialUpload.objects.filter(
            Q(property__name__in=DEMO_PROPERTY_NAMES)
            | Q(name__icontains="Demo")
            | Q(name__in=[f"{name} Demo Summary" for name in DEMO_PROPERTY_NAMES])
            | Q(name__in=[f"{name} Demo Receipt Batch" for name in DEMO_PROPERTY_NAMES])
        )
        demo_entries = FinancialEntry.objects.filter(
            Q(property_name__in=DEMO_PROPERTY_NAMES)
            | Q(sheet_name__icontains="Demo")
            | Q(upload__in=demo_uploads)
        )
        demo_receipts = AccountingReceipt.objects.filter(
            Q(property__name__in=DEMO_PROPERTY_NAMES)
            | Q(financial_entry__in=demo_entries)
        )
        demo_applications = HousingApplication.objects.filter(
            Q(property__name__in=DEMO_PROPERTY_NAMES)
            | Q(email__iendswith="@example.com")
        )
        demo_owner_intakes = PropertyOwnerIntake.objects.filter(
            Q(email__in=DEMO_OWNER_LEAD_EMAILS)
            | Q(email__iendswith="@example.com", company_name__icontains="Group")
            | Q(email__iendswith="@example.com", company_name__icontains="Housing")
            | Q(email__iendswith="@example.com", company_name__icontains="Portfolio")
        )
        demo_users = User.objects.filter(
            Q(username__in=DEMO_USERNAMES)
            | Q(username__startswith="demo-")
            | Q(email__iendswith="@example.com")
        )

        counts = {
            "properties": demo_properties.count(),
            "applications": demo_applications.count(),
            "receipts": demo_receipts.count(),
            "financial_entries": demo_entries.count(),
            "financial_uploads": demo_uploads.count(),
            "owner_intakes": demo_owner_intakes.count(),
            "users": demo_users.count(),
        }

        self.stdout.write("RentalReadyPro demo data cleanup preview")
        self.stdout.write("========================================")
        for label, count in counts.items():
            self.stdout.write(f"{label}: {count}")

        if not options["confirm"]:
            self.stdout.write("")
            self.stdout.write("Dry run only. No records were deleted.")
            self.stdout.write("Run again with --confirm to delete the selected demo data.")
            return

        with transaction.atomic():
            # Delete child/loose records first. Property deletion then cascades
            # remaining property-bound demo objects such as listings and room rents.
            deleted = {}
            deleted["receipts"] = demo_receipts.delete()[0]
            deleted["financial_entries"] = demo_entries.delete()[0]
            deleted["financial_uploads"] = demo_uploads.delete()[0]
            deleted["applications"] = demo_applications.delete()[0]
            deleted["properties"] = demo_properties.delete()[0]
            deleted["owner_intakes"] = demo_owner_intakes.delete()[0]
            deleted["users"] = demo_users.delete()[0]

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Demo data cleanup complete."))
        for label, count in deleted.items():
            self.stdout.write(f"{label} deleted: {count}")
