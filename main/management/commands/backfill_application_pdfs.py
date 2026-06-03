from io import BytesIO

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.utils import timezone
from reportlab.pdfgen import canvas

from main.models import HousingApplication, ApplicantDocument


class Command(BaseCommand):
    help = "Create or repair locked PDF documents for all housing applications"

    def handle(self, *args, **kwargs):
        created_count = 0
        repaired_count = 0
        skipped_count = 0

        applications = HousingApplication.objects.all().order_by("id")

        for app in applications:
            existing_doc = ApplicantDocument.objects.filter(
                application=app,
                document_type="application_pdf"
            ).first()

            if existing_doc and existing_doc.file:
                skipped_count += 1
                continue

            buffer = BytesIO()
            pdf = canvas.Canvas(buffer)

            y = 800
            lines = [
                "Bowling Legacy Housing Application",
                "",
                f"Applicant: {app.full_name}",
                f"Phone: {app.phone}",
                f"Email: {app.email}",
                f"Age: {app.age}",
                f"Property: {app.property.name if app.property else 'Not assigned'}",
                f"Income Source: {app.income_source}",
                f"Monthly Income: {app.monthly_income}",
                f"Submitted At: {app.created_at}",
                "",
                "Housing Need:",
                app.housing_need or "",
                "",
                "Additional Notes:",
                app.additional_notes or "",
            ]

            for line in lines:
                pdf.drawString(72, y, str(line)[:100])
                y -= 20

                if y < 72:
                    pdf.showPage()
                    y = 800

            pdf.showPage()
            pdf.save()

            buffer.seek(0)

            safe_name = app.full_name.replace(" ", "_").replace("/", "_")
            file_name = f"application_{app.id}_{safe_name}.pdf"

            if existing_doc:
                doc = existing_doc
                repaired_count += 1
            else:
                doc = ApplicantDocument(
                    application=app,
                    document_type="application_pdf",
                    name="Application PDF",
                )
                created_count += 1

            doc.status = "locked"
            doc.locked = True
            doc.submitted_at = timezone.now()

            doc.file.save(
                file_name,
                ContentFile(buffer.read()),
                save=False
            )

            doc.save()

        self.stdout.write(self.style.SUCCESS(
            f"Done. Created: {created_count}, repaired: {repaired_count}, skipped: {skipped_count}"
        ))
