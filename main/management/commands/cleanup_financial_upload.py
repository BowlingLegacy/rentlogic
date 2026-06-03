from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from main.models import FinancialUpload


class Command(BaseCommand):
    help = "Preview or delete financial uploads and their imported ledger entries."

    def add_arguments(self, parser):
        parser.add_argument(
            "--list",
            action="store_true",
            help="List recent financial uploads with IDs, names, properties, dates, and entry counts.",
        )
        parser.add_argument(
            "--upload-id",
            action="append",
            type=int,
            default=[],
            help="FinancialUpload ID to delete. Can be supplied more than once.",
        )
        parser.add_argument(
            "--name",
            action="append",
            default=[],
            help="Exact FinancialUpload name to delete. Can be supplied more than once.",
        )
        parser.add_argument(
            "--property-name",
            default="",
            help="Limit deletion by exact property name.",
        )
        parser.add_argument(
            "--confirm",
            action="store_true",
            help="Actually delete the selected upload records. Without this flag, this command is a dry run.",
        )
        parser.add_argument(
            "--delete-files",
            action="store_true",
            help="Also delete the uploaded spreadsheet files from storage.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=25,
            help="Number of recent uploads to show with --list.",
        )

    def handle(self, *args, **options):
        if options["list"]:
            self.list_uploads(options["limit"])
            return

        upload_ids = options["upload_id"]
        names = [name.strip() for name in options["name"] if name.strip()]

        if not upload_ids and not names:
            raise CommandError("Use --list first, then choose --upload-id or --name.")

        uploads = FinancialUpload.objects.select_related("property").prefetch_related("entries")

        if upload_ids:
            uploads = uploads.filter(id__in=upload_ids)

        if names:
            uploads = uploads.filter(name__in=names)

        property_name = options["property_name"].strip()
        if property_name:
            uploads = uploads.filter(property__name=property_name)

        selected_uploads = list(uploads.order_by("-uploaded_at"))
        if not selected_uploads:
            raise CommandError("No financial uploads matched those filters.")

        self.stdout.write("Financial upload cleanup preview")
        self.stdout.write("==============================")
        self.write_upload_rows(selected_uploads)

        entry_count = sum(upload.entries.count() for upload in selected_uploads)
        self.stdout.write(f"Uploads selected: {len(selected_uploads)}")
        self.stdout.write(f"Ledger entries selected: {entry_count}")

        if not options["confirm"]:
            self.stdout.write(self.style.WARNING("Dry run only. No uploads or entries were deleted."))
            self.stdout.write("Run again with --confirm to delete these records.")
            return

        files_to_delete = []
        if options["delete_files"]:
            files_to_delete = [upload.file for upload in selected_uploads if upload.file]

        for upload in selected_uploads:
            upload.delete()

        for upload_file in files_to_delete:
            upload_file.delete(save=False)

        self.stdout.write(self.style.SUCCESS("Financial upload cleanup complete."))
        self.stdout.write(f"Uploads deleted: {len(selected_uploads)}")
        self.stdout.write(f"Ledger entries deleted: {entry_count}")
        if options["delete_files"]:
            self.stdout.write(f"Uploaded spreadsheet files deleted: {len(files_to_delete)}")

    def list_uploads(self, limit):
        uploads = (
            FinancialUpload.objects
            .select_related("property")
            .prefetch_related("entries")
            .order_by("-uploaded_at")[:limit]
        )

        self.stdout.write("Recent financial uploads")
        self.stdout.write("========================")
        self.write_upload_rows(uploads)

    def write_upload_rows(self, uploads):
        for upload in uploads:
            uploaded_at = timezone.localtime(upload.uploaded_at).strftime("%Y-%m-%d %H:%M")
            parsed_at = (
                timezone.localtime(upload.parsed_at).strftime("%Y-%m-%d %H:%M")
                if upload.parsed_at
                else "not parsed"
            )
            property_name = upload.property.name if upload.property else "No property"
            self.stdout.write(
                f"ID {upload.id} | {upload.name} | {property_name} | "
                f"uploaded {uploaded_at} | parsed {parsed_at} | entries {upload.entries.count()}"
            )
