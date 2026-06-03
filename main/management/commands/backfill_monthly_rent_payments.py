from datetime import datetime
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from main.models import CurrentResidentRosterEntry, HousingApplication, Payment, Property, PropertyRoomRent


def clean_match_value(value):
    return "".join(character.lower() for character in str(value or "") if character.isalnum())


def normalized_room_label(room_unit_label):
    label = clean_match_value(room_unit_label)
    for prefix in ["room", "unit", "space", "apt", "apartment"]:
        if label.startswith(prefix) and len(label) > len(prefix):
            return label[len(prefix):]
    return label


def canonical_room_label(room_unit_label):
    clean_label = normalized_room_label(room_unit_label)
    if not clean_label:
        return str(room_unit_label or "").strip()
    if len(clean_label) == 1:
        return clean_label.upper()
    return clean_label.upper() if clean_label.isalpha() else clean_label


def payment_accounting_month(payment):
    if payment.service_month:
        return payment.service_month.replace(day=1)
    if payment.received_at:
        return timezone.localtime(payment.received_at).date().replace(day=1)
    return timezone.localtime(payment.created_at).date().replace(day=1)


class Command(BaseCommand):
    help = "Preview or create historical completed rent and utility payments for active room roster entries."

    def add_arguments(self, parser):
        parser.add_argument("--property-name", required=True, help="Exact property name.")
        parser.add_argument("--month", required=True, help="Accounting month in YYYY-MM format.")
        parser.add_argument(
            "--payment-method",
            default="cash",
            choices=[choice[0] for choice in Payment.PAYMENT_METHOD_CHOICES],
            help="Payment method to record for created payments.",
        )
        parser.add_argument(
            "--exclude-room",
            action="append",
            default=[],
            help="Room/unit label to leave unpaid. Can be supplied more than once.",
        )
        parser.add_argument(
            "--exclude-name",
            action="append",
            default=[],
            help="Resident name to leave unpaid. Case-insensitive exact match after cleanup.",
        )
        parser.add_argument(
            "--include-utilities",
            action="store_true",
            help="Also backfill monthly utility payments from room settings.",
        )
        parser.add_argument(
            "--payment-type",
            choices=["rent", "utility", "both"],
            help="Limit the backfill to rent, utilities, or both. Defaults to rent unless --include-utilities is used.",
        )
        parser.add_argument(
            "--confirm",
            action="store_true",
            help="Actually create missing payment records. Without this flag, this command is a dry run.",
        )

    def handle(self, *args, **options):
        property_name = options["property_name"].strip()
        property_obj = Property.objects.filter(name=property_name).first()
        if not property_obj:
            raise CommandError(f"Property not found: {property_name}")

        service_month = self.parse_month(options["month"])
        exclude_rooms = {normalized_room_label(room) for room in options["exclude_room"]}
        exclude_names = {clean_match_value(name) for name in options["exclude_name"]}
        include_utilities = options["include_utilities"]
        payment_type_option = options["payment_type"]
        payment_method = options["payment_method"]

        if payment_type_option:
            selected_payment_types = [payment_type_option] if payment_type_option != "both" else ["rent", "utility"]
        else:
            selected_payment_types = ["rent", "utility"] if include_utilities else ["rent"]

        room_settings = (
            PropertyRoomRent.objects
            .filter(property=property_obj, is_active=True)
            .order_by("room_unit_label")
        )
        if not room_settings.exists():
            raise CommandError(f"No active room rent settings found for {property_obj.name}.")

        self.stdout.write("Monthly payment backfill preview")
        self.stdout.write("================================")
        self.stdout.write(f"Property: {property_obj.name}")
        self.stdout.write(f"Month: {service_month.strftime('%B %Y')}")
        self.stdout.write(f"Payment method: {payment_method}")
        self.stdout.write(f"Payment types: {', '.join(selected_payment_types)}")
        if exclude_rooms:
            self.stdout.write(f"Excluded rooms: {', '.join(sorted(exclude_rooms))}")
        if exclude_names:
            self.stdout.write(f"Excluded names: {', '.join(sorted(exclude_names))}")

        planned = []
        skipped = []

        for setting in room_settings:
            room_label = canonical_room_label(setting.room_unit_label)
            roster_entry = self.find_roster_entry(property_obj, room_label)
            resident_name = roster_entry.full_name() if roster_entry else f"Room {room_label}"
            normalized_room = normalized_room_label(room_label)
            normalized_name = clean_match_value(resident_name)

            if normalized_room in exclude_rooms or normalized_name in exclude_names:
                skipped.append((room_label, resident_name, "excluded"))
                continue

            application = self.find_or_build_application(property_obj, room_label, roster_entry, setting)

            if "rent" in selected_payment_types:
                rent_amount = self.expected_rent_for_month(application, service_month, setting.monthly_rent)
                self.plan_missing_payment(planned, skipped, application, service_month, "rent", rent_amount, payment_method)

            if "utility" in selected_payment_types:
                utility_amount = self.expected_utility_for_month(application, service_month, setting.utility_monthly)
                self.plan_missing_payment(planned, skipped, application, service_month, "utility", utility_amount, payment_method)

        for room_label, resident_name, reason in skipped:
            self.stdout.write(f"SKIP | Room {room_label} | {resident_name} | {reason}")

        for application, payment_type, amount, description in planned:
            self.stdout.write(
                f"CREATE | Room {canonical_room_label(application.space_label)} | "
                f"{application.full_name} | {payment_type} | ${amount}"
            )

        self.stdout.write(f"Payments to create: {len(planned)}")

        if not options["confirm"]:
            self.stdout.write(self.style.WARNING("Dry run only. No payments were created."))
            self.stdout.write("Run again with --confirm to create these payment records.")
            return

        for application, payment_type, amount, description in planned:
            application.save()
            Payment.objects.create(
                application=application,
                payment_type=payment_type,
                payment_method=payment_method,
                description=description,
                notes="Historical payment backfilled from active room roster.",
                received_at=timezone.make_aware(datetime.combine(service_month, datetime.min.time())),
                service_month=service_month,
                months_covered=1,
                amount=amount,
                status="completed",
            )

        self.stdout.write(self.style.SUCCESS("Monthly payment backfill complete."))
        self.stdout.write(f"Payments created: {len(planned)}")

    def parse_month(self, value):
        try:
            return datetime.strptime(value, "%Y-%m").date().replace(day=1)
        except ValueError as exc:
            raise CommandError("Use --month in YYYY-MM format, for example --month 2026-05.") from exc

    def find_roster_entry(self, property_obj, room_label):
        target_room = normalized_room_label(room_label)
        for entry in CurrentResidentRosterEntry.objects.filter(property=property_obj, is_active=True):
            if normalized_room_label(entry.room_unit_label) == target_room:
                return entry
        return None

    def find_or_build_application(self, property_obj, room_label, roster_entry, setting):
        target_room = normalized_room_label(room_label)
        for application in HousingApplication.objects.filter(property=property_obj):
            if normalized_room_label(application.space_label) == target_room:
                return application

        resident_name = roster_entry.full_name() if roster_entry else f"Room {canonical_room_label(room_label)}"
        return HousingApplication(
            property=property_obj,
            full_name=resident_name,
            phone=roster_entry.phone if roster_entry else "",
            email=roster_entry.email if roster_entry else "",
            age=0,
            space_type="Room",
            space_label=canonical_room_label(room_label),
            monthly_rent=setting.monthly_rent,
            balance=Decimal("0.00"),
            rent_due_day=setting.rent_due_day,
            deposit_required=setting.deposit_required,
            deposit_paid=setting.deposit_paid,
            utility_monthly=setting.utility_monthly,
            utility_balance=Decimal("0.00"),
            income_source="Existing resident intake",
            monthly_income=Decimal("0.00"),
            housing_need="Historical resident file created for payment backfill.",
        )

    def plan_missing_payment(self, planned, skipped, application, service_month, payment_type, amount, payment_method):
        amount = Decimal(amount or "0.00")
        if amount <= 0:
            skipped.append((canonical_room_label(application.space_label), application.full_name, f"no {payment_type} amount"))
            return

        existing_total = Decimal("0.00")
        if application.pk:
            for payment in application.payments.filter(payment_type=payment_type, status="completed"):
                if payment_accounting_month(payment) == service_month:
                    existing_total += payment.amount
        missing_amount = max(amount - existing_total, Decimal("0.00"))
        if missing_amount <= 0:
            skipped.append((canonical_room_label(application.space_label), application.full_name, f"{payment_type} already paid"))
            return

        description = f"Historical {service_month.strftime('%B %Y')} {payment_type} payment"
        planned.append((application, payment_type, missing_amount, description))

    def expected_rent_for_month(self, application, service_month, default_amount):
        if (
            application.lease_start_date
            and application.move_in_rent_charge > 0
            and application.lease_start_date.year == service_month.year
            and application.lease_start_date.month == service_month.month
        ):
            return application.move_in_rent_charge
        return default_amount

    def expected_utility_for_month(self, application, service_month, default_amount):
        if (
            application.lease_start_date
            and application.move_in_utility_charge > 0
            and application.lease_start_date.year == service_month.year
            and application.lease_start_date.month == service_month.month
        ):
            return application.move_in_utility_charge
        return default_amount
