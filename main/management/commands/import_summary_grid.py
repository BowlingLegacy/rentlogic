from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from main.models import FinancialUpload, Property
from main.views import (
    create_financial_entry_from_import,
    money,
    normalized_header,
    parse_month_header,
    read_financial_upload_rows,
    should_skip_summary_category,
    summary_category_entry_type,
)


IGNORED_T12_SUMMARY_CATEGORIES = {
    "resident deposit",
    "resident deposits",
    "security deposit",
    "security deposits",
    "utility account",
    "utility accounts",
}


class Command(BaseCommand):
    help = "Import a monthly summary sheet where categories are down column A and months are across row 1."

    def add_arguments(self, parser):
        parser.add_argument("--property-name", required=True, help="Exact property name.")
        parser.add_argument("--year", type=int, required=True, help="Summary year, for example 2026.")
        parser.add_argument("--upload-id", type=int, help="FinancialUpload ID to import.")
        parser.add_argument("--upload-name", help="FinancialUpload name to import. Uses newest matching upload.")
        parser.add_argument("--sheet-name", help="Worksheet/tab name. Defaults to first sheet.")
        parser.add_argument("--category-column", help="Category column. Defaults to first column.")
        parser.add_argument("--default-entry-type", default="operating_expense")
        parser.add_argument("--confirm", action="store_true", help="Write entries. Without this flag, only previews.")

    def handle(self, *args, **options):
        property_obj = Property.objects.filter(name=options["property_name"].strip()).first()
        if not property_obj:
            raise CommandError(f"Property not found: {options['property_name']}")

        upload = self.find_upload(property_obj, options)
        sheet_name, headers, rows = read_financial_upload_rows(upload, selected_sheet_name=options.get("sheet_name"))
        if not headers:
            raise CommandError("No headers found in upload.")

        category_column = options.get("category_column") or headers[0]
        if category_column not in headers:
            raise CommandError(f"Category column not found: {category_column}")

        month_columns = [header for header in headers if parse_month_header(header)]
        if not month_columns:
            raise CommandError("No month columns found. Expected headers like January, February, March, April, May.")

        summary_categories = [
            str(row["data"].get(category_column, "") or "").strip()
            for row in rows
        ]

        planned = []
        skipped_rows = 0
        skipped_duplicate_entries = 0
        seen_entries = set()
        for row in rows:
            category = str(row["data"].get(category_column, "") or "").strip()
            clean_category = normalized_header(category)
            if clean_category in IGNORED_T12_SUMMARY_CATEGORIES or should_skip_summary_category(category, summary_categories):
                skipped_rows += 1
                continue

            row_created = 0
            for column_name in month_columns:
                month_number = parse_month_header(column_name)
                amount = money(row["data"].get(column_name))
                if amount == Decimal("0.00"):
                    continue

                entry_type = summary_category_entry_type(category, options["default_entry_type"])
                if not entry_type:
                    continue

                duplicate_key = (month_number, entry_type, clean_category, abs(amount))
                if duplicate_key in seen_entries:
                    skipped_duplicate_entries += 1
                    continue

                seen_entries.add(duplicate_key)
                planned.append((row, month_number, column_name, entry_type, category, amount))
                row_created += 1

            if row_created == 0:
                skipped_rows += 1

        self.stdout.write("Summary grid import preview")
        self.stdout.write("===========================")
        self.stdout.write(f"Property: {property_obj.name}")
        self.stdout.write(f"Upload: {upload.id} | {upload.name}")
        self.stdout.write(f"Sheet: {sheet_name}")
        self.stdout.write(f"Category column: {category_column}")
        self.stdout.write(f"Month columns: {', '.join(month_columns)}")
        self.stdout.write(f"Rows skipped: {skipped_rows}")
        self.stdout.write(f"Duplicate entries skipped: {skipped_duplicate_entries}")
        self.stdout.write(f"Entries selected: {len(planned)}")

        totals = {}
        for _row, month_number, _column_name, entry_type, category, amount in planned:
            key = (month_number, entry_type)
            totals[key] = totals.get(key, Decimal("0.00")) + abs(amount)
            self.stdout.write(f"{month_number:02d} | {entry_type} | {category} | ${abs(amount)}")

        self.stdout.write("")
        self.stdout.write("Monthly totals")
        self.stdout.write("--------------")
        for (month_number, entry_type), amount in sorted(totals.items()):
            self.stdout.write(f"{month_number:02d} | {entry_type} | ${amount}")

        if not options["confirm"]:
            self.stdout.write(self.style.WARNING("Dry run only. No entries were changed."))
            self.stdout.write("Run again with --confirm to replace this upload's ledger entries.")
            return

        upload.entries.all().delete()
        created = 0
        for row, month_number, column_name, entry_type, category, amount in planned:
            entry = create_financial_entry_from_import(
                upload,
                property_obj,
                sheet_name,
                row,
                timezone.datetime(options["year"], month_number, 1).date(),
                entry_type,
                category,
                f"{category} - {column_name} summary",
                amount,
            )
            if entry:
                created += 1

        upload.parsed_at = timezone.now()
        upload.save(update_fields=["parsed_at"])
        self.stdout.write(self.style.SUCCESS("Summary grid import complete."))
        self.stdout.write(f"Entries created: {created}")

    def find_upload(self, property_obj, options):
        if options.get("upload_id"):
            upload = FinancialUpload.objects.filter(id=options["upload_id"], property=property_obj).first()
            if not upload:
                raise CommandError(f"Upload not found for {property_obj.name}: {options['upload_id']}")
            return upload

        queryset = FinancialUpload.objects.filter(property=property_obj).order_by("-uploaded_at")
        if options.get("upload_name"):
            queryset = queryset.filter(name__icontains=options["upload_name"].strip())

        upload = queryset.first()
        if not upload:
            raise CommandError("No matching upload found. Use --upload-id or --upload-name.")
        return upload
