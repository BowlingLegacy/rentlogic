from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from main.models import ApplicantDocument, HousingApplication, Payment, Property, ResidentMessage, User


DEFAULT_PRESERVE_NAMES = {"Felicia Valdez"}


class Command(BaseCommand):
    help = (
        "Preview or delete test portal data: applications, resident messages, "
        "incoming documents, payment records, and non-staff tenant users linked "
        "to deleted applications."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--confirm",
            action="store_true",
            help="Actually delete the selected records. Without this flag, this command is a dry run.",
        )
        parser.add_argument(
            "--preserve-email",
            action="append",
            default=[],
            help=(
                "Application/user email to keep. Can be supplied more than once, "
                "for example --preserve-email michael@example.com."
            ),
        )
        parser.add_argument(
            "--preserve-name",
            action="append",
            default=[],
            help="Application full name to keep. Can be supplied more than once.",
        )
        parser.add_argument(
            "--preserve-payment-id",
            action="append",
            type=int,
            default=[],
            help="Payment ID to keep. The payment's application is also kept.",
        )
        parser.add_argument(
            "--preserve-only-completed-one-dollar-payment",
            action="store_true",
            help=(
                "Keep the application linked to the only completed $1.00 payment. "
                "Stops if zero or multiple matching payments exist."
            ),
        )
        parser.add_argument(
            "--keep-users",
            action="store_true",
            help="Keep linked tenant users even when their selected applications are deleted.",
        )
        parser.add_argument(
            "--delete-files",
            action="store_true",
            help="Also delete uploaded document files from storage for deleted ApplicantDocument records.",
        )
        parser.add_argument(
            "--delete-property-name",
            action="append",
            default=[],
            help=(
                "Exact Property name to delete. Can be supplied more than once. "
                "This is separate from application cleanup and should only be used for named test properties."
            ),
        )

    def handle(self, *args, **options):
        confirm = options["confirm"]
        delete_files = options["delete_files"]
        keep_users = options["keep_users"]
        preserve_emails = {
            email.strip().lower()
            for email in options["preserve_email"]
            if email and email.strip()
        }
        preserve_names = {
            name.strip()
            for name in options["preserve_name"]
            if name and name.strip()
        }
        preserve_names.update(DEFAULT_PRESERVE_NAMES)
        preserve_payment_ids = set(options["preserve_payment_id"])
        delete_property_names = {
            property_name.strip()
            for property_name in options["delete_property_name"]
            if property_name and property_name.strip()
        }

        if options["preserve_only_completed_one_dollar_payment"]:
            one_dollar_payments = Payment.objects.filter(
                amount=Decimal("1.00"),
                status="completed",
            ).select_related("application")

            if one_dollar_payments.count() != 1:
                matching_ids = ", ".join(str(payment.id) for payment in one_dollar_payments)
                raise CommandError(
                    "Expected exactly one completed $1.00 payment to preserve. "
                    f"Found {one_dollar_payments.count()}. Matching payment IDs: {matching_ids or 'none'}."
                )

            preserve_payment_ids.add(one_dollar_payments.first().id)

        preserved_payments = Payment.objects.filter(id__in=preserve_payment_ids).select_related("application")
        missing_payment_ids = preserve_payment_ids - set(preserved_payments.values_list("id", flat=True))
        if missing_payment_ids:
            raise CommandError(
                f"Cannot preserve missing payment IDs: {', '.join(str(payment_id) for payment_id in sorted(missing_payment_ids))}."
            )
        preserve_application_ids = set(preserved_payments.values_list("application_id", flat=True))

        applications = HousingApplication.objects.select_related("user").all()
        for email in preserve_emails:
            applications = applications.exclude(email__iexact=email)
        for name in preserve_names:
            applications = applications.exclude(full_name__iexact=name)
        if preserve_application_ids:
            applications = applications.exclude(id__in=preserve_application_ids)

        application_ids = list(applications.values_list("id", flat=True))
        linked_user_ids = set(
            applications
            .exclude(user__isnull=True)
            .values_list("user_id", flat=True)
        )

        users = User.objects.filter(
            id__in=linked_user_ids,
            is_staff=False,
            is_superuser=False,
            role="tenant",
        )

        for email in preserve_emails:
            users = users.exclude(email__iexact=email)

        documents = ApplicantDocument.objects.filter(application_id__in=application_ids)
        messages = ResidentMessage.objects.filter(application_id__in=application_ids)
        payments = Payment.objects.filter(application_id__in=application_ids)
        properties = Property.objects.filter(name__in=delete_property_names).order_by("name")
        missing_property_names = delete_property_names - set(properties.values_list("name", flat=True))
        if missing_property_names:
            raise CommandError(
                "Cannot delete missing property names: "
                f"{', '.join(sorted(missing_property_names))}."
            )

        self.stdout.write("Portal cleanup preview")
        self.stdout.write("======================")
        self.stdout.write(f"Preserved emails: {', '.join(sorted(preserve_emails)) or 'none'}")
        self.stdout.write(f"Preserved names: {', '.join(sorted(preserve_names)) or 'none'}")
        self.stdout.write(f"Preserved payment IDs: {', '.join(str(payment.id) for payment in preserved_payments) or 'none'}")
        if preserved_payments:
            self.stdout.write("Preserved payment applications:")
            for payment in preserved_payments:
                self.stdout.write(
                    f"  Payment {payment.id}: ${payment.amount} {payment.get_status_display()} "
                    f"for {payment.application.full_name}"
                )
        self.stdout.write(f"Applications selected: {len(application_ids)}")
        self.stdout.write(f"Incoming documents selected: {documents.count()}")
        self.stdout.write(f"Resident messages selected: {messages.count()}")
        self.stdout.write(f"Payment records selected: {payments.count()}")
        self.stdout.write(f"Linked tenant users selected: {0 if keep_users else users.count()}")
        self.stdout.write(f"Properties selected by exact name: {properties.count()}")
        for property_obj in properties:
            self.stdout.write(f"  Property {property_obj.id}: {property_obj.name}")
        if keep_users:
            self.stdout.write("Linked tenant users will be kept.")

        if not confirm:
            self.stdout.write("")
            self.stdout.write(self.style.WARNING("Dry run only. No records were deleted."))
            self.stdout.write("Run again with --confirm to delete these records.")
            return

        if not application_ids and not properties.exists():
            self.stdout.write(self.style.SUCCESS("No matching portal records found."))
            return

        document_files = []
        if delete_files:
            document_files = [
                document.file
                for document in documents
                if document.file
            ]

        selected_counts = {
            "applications": len(application_ids),
            "documents": documents.count(),
            "messages": messages.count(),
            "payments": payments.count(),
            "users": 0 if keep_users else users.count(),
            "properties": properties.count(),
        }

        try:
            with transaction.atomic():
                payments.delete()
                messages.delete()
                documents.delete()
                applications.delete()
                if not keep_users:
                    users.delete()
                properties.delete()

            for document_file in document_files:
                document_file.delete(save=False)

        except Exception as exc:
            raise CommandError(f"Cleanup failed: {exc}") from exc

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Cleanup complete."))
        self.stdout.write(f"Applications deleted: {selected_counts['applications']}")
        self.stdout.write(f"Incoming documents deleted: {selected_counts['documents']}")
        self.stdout.write(f"Resident messages deleted: {selected_counts['messages']}")
        self.stdout.write(f"Payment records deleted: {selected_counts['payments']}")
        self.stdout.write(f"Linked tenant users deleted: {selected_counts['users']}")
        self.stdout.write(f"Properties deleted: {selected_counts['properties']}")
        if delete_files:
            self.stdout.write(f"Uploaded document files deleted: {len(document_files)}")
