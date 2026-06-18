from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from main.models import HousingApplication, Property, SignedDocument


class Command(BaseCommand):
    help = "Issue a platform lease update to resident inboxes."

    def add_arguments(self, parser):
        parser.add_argument(
            "--confirm",
            action="store_true",
            help="Required to create lease update records.",
        )
        parser.add_argument(
            "--property-name",
            default="",
            help="Property name to issue the lease update for.",
        )

    def handle(self, *args, **options):
        if not options["confirm"]:
            raise CommandError("Add --confirm to issue lease update documents.")

        property_name = options["property_name"]
        property_obj = Property.objects.filter(name__iexact=property_name).first()

        if not property_obj:
            raise CommandError(f'Property not found: "{property_name}"')

        applications = HousingApplication.objects.filter(
            property=property_obj,
        ).order_by("space_label", "full_name")

        created = 0
        skipped = 0
        title = "Resident Lease Agreement - June 2026 Platform Update"

        for application in applications:
            existing_unsigned = SignedDocument.objects.filter(
                application=application,
                document_type="lease",
                title=title,
                locked=False,
            ).exists()

            if existing_unsigned:
                skipped += 1
                continue

            SignedDocument.objects.create(
                application=application,
                document_type="lease",
                title=title,
                lease_sent_date=timezone.localdate(),
                landlord_name="Michael Bowling",
                landlord_signature="Michael Bowling",
            )
            created += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Issued {created} lease update document(s); skipped {skipped} existing unsigned update(s)."
            )
        )
