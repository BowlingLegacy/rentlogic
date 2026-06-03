from collections import defaultdict
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from main.models import (
    ApplicantDocument,
    ExistingResidentIntake,
    HousingApplication,
    Payment,
    RentHistory,
    ResidentMessage,
    ResidentUtilitySetup,
    SignedDocument,
)
from main.views import normalized_room_label, payment_service_month


def name_tokens(value):
    return {
        token.lower()
        for token in str(value or "").replace("/", " ").split()
        if token.strip()
    }


def names_are_compatible(left, right):
    left_tokens = name_tokens(left)
    right_tokens = name_tokens(right)

    if not left_tokens or not right_tokens:
        return False

    if left_tokens.issubset(right_tokens) or right_tokens.issubset(left_tokens):
        return True

    left_parts = str(left or "").strip().split()
    right_parts = str(right or "").strip().split()
    if len(left_parts) >= 2 and len(right_parts) >= 2:
        left_first, left_last = left_parts[0].lower(), left_parts[-1].lower()
        right_first, right_last = right_parts[0].lower(), right_parts[-1].lower()
        return left_last == right_last and (
            left_first.startswith(right_first[:3]) or right_first.startswith(left_first[:3])
        )

    return False


def payment_key(payment):
    accounting_month = payment_service_month(payment)
    return (
        payment.payment_type,
        payment.status,
        accounting_month,
        payment.amount,
    )


class Command(BaseCommand):
    help = "Preview or merge duplicate resident files and duplicate same-month payment records."

    def add_arguments(self, parser):
        parser.add_argument("--property-name", help="Limit cleanup to one property name.")
        parser.add_argument("--room", help="Limit cleanup to one room/unit label.")
        parser.add_argument("--confirm", action="store_true", help="Actually merge/delete duplicate records.")

    def handle(self, *args, **options):
        applications = HousingApplication.objects.select_related("property", "user").all()

        if options["property_name"]:
            applications = applications.filter(property__name=options["property_name"].strip())
            if not applications.exists():
                raise CommandError(f"No resident files found for property: {options['property_name']}")

        if options["room"]:
            target_room = normalized_room_label(options["room"])
            applications = [
                application
                for application in applications
                if normalized_room_label(application.space_label) == target_room
            ]
        else:
            applications = list(applications)

        duplicate_groups = self.find_duplicate_application_groups(applications)
        duplicate_payments = self.find_duplicate_payments(applications)

        self.stdout.write("Resident duplicate cleanup preview")
        self.stdout.write("==================================")
        self.stdout.write(f"Duplicate resident groups: {len(duplicate_groups)}")

        for primary, duplicates in duplicate_groups:
            self.stdout.write(
                f"KEEP app {primary.id} | {primary.property.name if primary.property else 'No Property'} | "
                f"Room {primary.space_label} | {primary.full_name} | user {primary.user_id or '-'}"
            )
            for duplicate in duplicates:
                self.stdout.write(
                    f"  MERGE app {duplicate.id} | Room {duplicate.space_label} | "
                    f"{duplicate.full_name} | user {duplicate.user_id or '-'}"
                )

        self.stdout.write("")
        self.stdout.write(f"Duplicate same-month payments: {len(duplicate_payments)}")
        for keep_payment, delete_payments in duplicate_payments:
            self.stdout.write(
                f"KEEP payment {keep_payment.id} | app {keep_payment.application_id} | "
                f"{keep_payment.payment_type} | ${keep_payment.amount} | {payment_service_month(keep_payment)}"
            )
            for payment in delete_payments:
                self.stdout.write(
                    f"  DELETE payment {payment.id} | app {payment.application_id} | "
                    f"{payment.payment_type} | ${payment.amount} | {payment_service_month(payment)}"
                )

        if not options["confirm"]:
            self.stdout.write(self.style.WARNING("Dry run only. No records were changed."))
            self.stdout.write("Run again with --confirm to merge/delete these duplicate records.")
            return

        with transaction.atomic():
            for primary, duplicates in duplicate_groups:
                for duplicate in duplicates:
                    self.merge_application(primary, duplicate)

            refreshed_applications = HousingApplication.objects.select_related("property", "user").all()
            if options["property_name"]:
                refreshed_applications = refreshed_applications.filter(property__name=options["property_name"].strip())
            if options["room"]:
                target_room = normalized_room_label(options["room"])
                refreshed_applications = [
                    application
                    for application in refreshed_applications
                    if normalized_room_label(application.space_label) == target_room
                ]
            else:
                refreshed_applications = list(refreshed_applications)

            for _keep_payment, delete_payments in self.find_duplicate_payments(refreshed_applications):
                Payment.objects.filter(id__in=[payment.id for payment in delete_payments]).delete()

        self.stdout.write(self.style.SUCCESS("Resident duplicate cleanup complete."))

    def find_duplicate_application_groups(self, applications):
        by_property_room = defaultdict(list)
        for application in applications:
            by_property_room[(application.property_id, normalized_room_label(application.space_label))].append(application)

        groups = []
        for room_applications in by_property_room.values():
            unprocessed = list(room_applications)
            while unprocessed:
                seed = unprocessed.pop(0)
                matches = [seed]
                remaining = []

                for candidate in unprocessed:
                    if names_are_compatible(seed.full_name, candidate.full_name):
                        matches.append(candidate)
                    else:
                        remaining.append(candidate)

                unprocessed = remaining
                if len(matches) > 1:
                    primary = self.choose_primary(matches)
                    duplicates = [application for application in matches if application.id != primary.id]
                    groups.append((primary, duplicates))

        return groups

    def choose_primary(self, applications):
        return sorted(
            applications,
            key=lambda application: (
                application.user_id is None,
                -int(application.user.has_usable_password()) if application.user_id else 0,
                -application.signed_documents.filter(locked=True).count(),
                -application.payments.count(),
                application.id,
            ),
        )[0]

    def find_duplicate_payments(self, applications):
        application_ids = [application.id for application in applications if application.id]
        by_key = defaultdict(list)

        for payment in Payment.objects.filter(application_id__in=application_ids).select_related("application").order_by("id"):
            if payment.amount <= Decimal("0.00"):
                continue
            by_key[(payment.application.property_id, normalized_room_label(payment.application.space_label), payment_key(payment))].append(payment)

        duplicate_groups = []
        for payments in by_key.values():
            if len(payments) <= 1:
                continue

            keep_payment = sorted(
                payments,
                key=lambda payment: (
                    payment.payment_method not in ["stripe", "stripe_card"],
                    payment.id,
                ),
            )[0]
            duplicate_groups.append((keep_payment, [payment for payment in payments if payment.id != keep_payment.id]))

        return duplicate_groups

    def merge_application(self, primary, duplicate):
        Payment.objects.filter(application=duplicate).update(application=primary)
        ApplicantDocument.objects.filter(application=duplicate).update(application=primary)
        SignedDocument.objects.filter(application=duplicate).update(application=primary)
        RentHistory.objects.filter(application=duplicate).update(application=primary)
        ResidentMessage.objects.filter(application=duplicate).update(application=primary)

        for setup in ResidentUtilitySetup.objects.filter(application=duplicate):
            if ResidentUtilitySetup.objects.filter(application=primary, vendor=setup.vendor).exists():
                setup.delete()
            else:
                setup.application = primary
                setup.save(update_fields=["application"])

        for intake in ExistingResidentIntake.objects.filter(application=duplicate):
            if ExistingResidentIntake.objects.filter(application=primary).exclude(id=intake.id).exists():
                intake.application = None
            else:
                intake.application = primary
            intake.save(update_fields=["application"])

        if not primary.email and duplicate.email:
            primary.email = duplicate.email
        if not primary.phone and duplicate.phone:
            primary.phone = duplicate.phone
        if primary.balance > duplicate.balance:
            primary.balance = duplicate.balance
        if primary.utility_balance > duplicate.utility_balance:
            primary.utility_balance = duplicate.utility_balance

        primary.save(update_fields=["email", "phone", "balance", "utility_balance"])
        duplicate.delete()
