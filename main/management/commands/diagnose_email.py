from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone


class Command(BaseCommand):
    help = "Print email configuration status and optionally send a test email."

    def add_arguments(self, parser):
        parser.add_argument("--to", help="Email address to receive a test email.")
        parser.add_argument("--send", action="store_true", help="Send the test email.")

    def handle(self, *args, **options):
        self.stdout.write("RentalReadyPro email diagnostic")
        self.stdout.write("==============================")
        self.stdout.write(f"EMAIL_BACKEND: {settings.EMAIL_BACKEND}")
        self.stdout.write(f"EMAIL_HOST: {settings.EMAIL_HOST}")
        self.stdout.write(f"EMAIL_PORT: {settings.EMAIL_PORT}")
        self.stdout.write(f"EMAIL_USE_TLS: {settings.EMAIL_USE_TLS}")
        self.stdout.write(f"EMAIL_HOST_USER set: {bool(settings.EMAIL_HOST_USER)}")
        self.stdout.write(f"EMAIL_HOST_PASSWORD set: {bool(settings.EMAIL_HOST_PASSWORD)}")
        self.stdout.write(f"DEFAULT_FROM_EMAIL: {settings.DEFAULT_FROM_EMAIL or '-'}")
        self.stdout.write(f"DEMO_MODE: {getattr(settings, 'DEMO_MODE', False)}")

        if not options["send"]:
            self.stdout.write("")
            self.stdout.write("No email was sent. Add --send --to you@example.com to send a live test.")
            return

        recipient = options.get("to")
        if not recipient:
            raise CommandError("Use --to EMAIL when --send is provided.")

        if not settings.EMAIL_HOST_USER or not settings.EMAIL_HOST_PASSWORD:
            raise CommandError("EMAIL_HOST_USER and EMAIL_HOST_PASSWORD must both be set before sending email.")

        subject = "RentalReadyPro email test"
        body = (
            "This is a RentalReadyPro email delivery test.\n\n"
            f"Sent at: {timezone.now().isoformat()}\n"
            f"Backend: {settings.EMAIL_BACKEND}\n"
            f"From: {settings.DEFAULT_FROM_EMAIL}\n"
        )
        sent_count = send_mail(
            subject,
            body,
            settings.DEFAULT_FROM_EMAIL,
            [recipient],
            fail_silently=False,
        )
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"Email send call completed. Messages accepted by backend: {sent_count}"))
