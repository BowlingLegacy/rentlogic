from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from main.models import Payment, Property


def clean_match_value(value):
    return "".join(character.lower() for character in str(value or "") if character.isalnum())


def normalized_room_label(room_unit_label):
    label = clean_match_value(room_unit_label)
    for prefix in ["room", "unit", "space", "apt", "apartment"]:
        if label.startswith(prefix) and len(label) > len(prefix):
            return label[len(prefix):]
    return label


def parse_month(value):
    try:
        return datetime.strptime(value, "%Y-%m").date().replace(day=1)
    except ValueError as exc:
        raise CommandError("Use months in YYYY-MM format, for example --from-month 2026-05.") from exc


def payment_accounting_month(payment):
    if payment.service_month:
        return payment.service_month.replace(day=1)
    if payment.received_at:
        return timezone.localtime(payment.received_at).date().replace(day=1)
    return timezone.localtime(payment.created_at).date().replace(day=1)


class Command(BaseCommand):
    help = "Preview or move selected payments from one accounting month to another."

    def add_arguments(self, parser):
        parser.add_argument("--property-name", required=True, help="Exact property name.")
        parser.add_argument("--from-month", required=True, help="Current accounting month in YYYY-MM format.")
        parser.add_argument("--to-month", required=True, help="Correct accounting month in YYYY-MM format.")
        parser.add_argument("--payment-type", default="rent", choices=[choice[0] for choice in Payment.PAYMENT_TYPE_CHOICES])
        parser.add_argument("--room", default="", help="Limit by resident room/unit label.")
        parser.add_argument("--resident-name", default="", help="Limit by resident name contains.")
        parser.add_argument("--amount", default="", help="Optional exact amount to limit which payment moves.")
        parser.add_argument("--confirm", action="store_true", help="Actually update selected payments.")

    def handle(self, *args, **options):
        property_obj = Property.objects.filter(name=options["property_name"].strip()).first()
        if not property_obj:
            raise CommandError(f"Property not found: {options['property_name']}")

        from_month = parse_month(options["from_month"])
        to_month = parse_month(options["to_month"])
        payment_type = options["payment_type"]
        target_room = normalized_room_label(options["room"])
        resident_name = options["resident_name"].strip().lower()
        exact_amount = self.parse_amount(options["amount"])

        payments = (
            Payment.objects
            .select_related("application", "application__property")
            .filter(application__property=property_obj, payment_type=payment_type, status="completed")
            .order_by("application__space_label", "application__full_name", "created_at", "id")
        )

        selected = []
        for payment in payments:
            application = payment.application
            if payment_accounting_month(payment) != from_month:
                continue
            if target_room and normalized_room_label(application.space_label) != target_room:
                continue
            if resident_name and resident_name not in application.full_name.lower():
                continue
            if exact_amount is not None and payment.amount != exact_amount:
                continue
            selected.append(payment)

        self.stdout.write("Payment service month move preview")
        self.stdout.write("==================================")
        self.stdout.write(f"Property: {property_obj.name}")
        self.stdout.write(f"Payment type: {payment_type}")
        self.stdout.write(f"From: {from_month.strftime('%B %Y')}")
        self.stdout.write(f"To: {to_month.strftime('%B %Y')}")

        for payment in selected:
            application = payment.application
            self.stdout.write(
                f"MOVE | payment {payment.id} | Room {application.space_label or '-'} | "
                f"{application.full_name} | ${payment.amount} | "
                f"received {payment.received_at or payment.created_at}"
            )

        self.stdout.write(f"Payments selected: {len(selected)}")

        if not options["confirm"]:
            self.stdout.write(self.style.WARNING("Dry run only. No payments were changed."))
            self.stdout.write("Run again with --confirm to move these payments.")
            return

        for payment in selected:
            payment.service_month = to_month
            payment.notes = (
                f"{payment.notes}\n"
                f"Service month corrected from {from_month.strftime('%B %Y')} "
                f"to {to_month.strftime('%B %Y')}."
            ).strip()
            payment.save(update_fields=["service_month", "notes"])

        self.stdout.write(self.style.SUCCESS("Payment service month move complete."))
        self.stdout.write(f"Payments updated: {len(selected)}")

    def parse_amount(self, value):
        if not value:
            return None
        try:
            return Decimal(str(value).replace("$", "").replace(",", "").strip()).quantize(Decimal("0.01"))
        except (InvalidOperation, ValueError) as exc:
            raise CommandError("Use --amount as a decimal amount, for example --amount 506.00.") from exc
