from collections import defaultdict
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q, Sum

from main.models import FinancialEntry, Payment, Property
from main.views import T12_INCOME_PAYMENT_TYPES, payment_amount_for_month, t12_report_rows


class Command(BaseCommand):
    help = "Show the exact payment and financial-entry inputs used by the T-12 report."

    def add_arguments(self, parser):
        parser.add_argument("--property-name", required=True, help="Exact property name.")
        parser.add_argument("--year", type=int, required=True, help="Report year, for example 2026.")

    def handle(self, *args, **options):
        property_name = options["property_name"].strip()
        year = options["year"]
        property_obj = Property.objects.filter(name=property_name).first()
        if not property_obj:
            raise CommandError(f"Property not found: {property_name}")

        self.stdout.write("T-12 diagnostic")
        self.stdout.write("================")
        self.stdout.write(f"Property: {property_obj.name}")
        self.stdout.write(f"Year: {year}")
        self.stdout.write("")

        payments = list(
            Payment.objects
            .select_related("application")
            .filter(application__property=property_obj, status="completed")
        )
        entries = (
            FinancialEntry.objects
            .select_related("upload")
            .filter(Q(upload__property=property_obj) | Q(property_name=property_obj.name))
            .filter(Q(year=year) | Q(entry_date__year=year))
            .order_by("month", "entry_type", "category", "description")
        )

        self.stdout.write("Payment ledger income by month")
        self.stdout.write("------------------------------")
        for month in range(1, 13):
            month_total = payment_amount_for_month(payments, year, month, T12_INCOME_PAYMENT_TYPES)
            if month_total:
                self.stdout.write(f"{month:02d}: ${month_total}")
                by_type = defaultdict(Decimal)
                for payment_type in T12_INCOME_PAYMENT_TYPES:
                    amount = payment_amount_for_month(payments, year, month, [payment_type])
                    if amount:
                        by_type[payment_type] += amount
                for payment_type, amount in sorted(by_type.items()):
                    self.stdout.write(f"    {payment_type}: ${amount}")

        self.stdout.write("")
        self.stdout.write("Financial entries by month/type")
        self.stdout.write("-------------------------------")
        for month in range(1, 13):
            month_entries = entries.filter(Q(month=month) | Q(entry_date__month=month))
            if not month_entries.exists():
                continue
            self.stdout.write(f"{month:02d}:")
            totals = (
                month_entries
                .values("entry_type")
                .annotate(total=Sum("amount"))
                .order_by("entry_type")
            )
            for total in totals:
                self.stdout.write(f"    {total['entry_type']}: ${total['total']}")
            for entry in month_entries:
                self.stdout.write(
                    f"        {entry.entry_type} | {entry.category} | ${entry.amount} | "
                    f"{entry.upload.name if entry.upload else 'No upload'}"
                )

        self.stdout.write("")
        self.stdout.write("T-12 rows after current report rules")
        self.stdout.write("------------------------------------")
        months, totals = t12_report_rows_for_property(property_obj, year)
        for index, row in enumerate(months, start=1):
            if any(row[key] for key in [
                "online_income",
                "spreadsheet_income",
                "operating_expenses",
                "debt_service",
                "capital_expenses",
            ]):
                self.stdout.write(
                    f"{index:02d} {row['month_name']}: source={row['income_source'] or '-'} "
                    f"online=${row['online_income']} spreadsheet=${row['spreadsheet_income']} "
                    f"income=${row['total_income']} op_ex=${row['operating_expenses']} "
                    f"debt=${row['debt_service']} noi=${row['net_operating_income']} "
                    f"cash_flow=${row['cash_flow_after_debt']}"
                )

        self.stdout.write("")
        self.stdout.write("Totals")
        self.stdout.write("------")
        for key, value in totals.items():
            self.stdout.write(f"{key}: ${value}")


def t12_report_rows_for_property(property_obj, year):
    class PropertyScopedUser:
        is_superuser = True
        role = "admin"

    return t12_report_rows(PropertyScopedUser(), year, Property.objects.filter(id=property_obj.id))
