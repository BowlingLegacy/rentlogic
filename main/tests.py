from decimal import Decimal
from datetime import date, datetime
from io import BytesIO, StringIO
from unittest.mock import patch

from django.contrib import admin
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db.models import Sum
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import AccountingReceipt, ApplicantDocument, BlogComment, BlogPost, CompanyMailboxConnection, CurrentResidentRosterEntry, ExistingResidentIntake, ExpenseCategory, FinancialEntry, FinancialUpload, HousingApplication, LandlordIntake, Payment, Property, PropertyOnboardingDocument, PropertyOwnerIntake, PropertyRoomRent, PropertyUtilityVendor, RentHistory, RentalListing, RentalListingChannel, ReportTemplate, ResidentMessage, ResidentMessageReply, ResidentUtilitySetup, SignedDocument, SmsMessageLog, User
from .views import apply_completed_payment_to_balance, ensure_existing_resident_portal_application, payment_amount_for_month, prorated_monthly_charge, rent_roll_rows_for_properties, t12_report_rows


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    STRIPE_SECRET_KEY="sk_test_local",
    STRIPE_PUBLIC_KEY="pk_test_local",
    STRIPE_WEBHOOK_SECRET="whsec_local",
    MICROSOFT_GRAPH_CLIENT_ID="client-local",
    MICROSOFT_GRAPH_CLIENT_SECRET="secret-local",
    MICROSOFT_GRAPH_REDIRECT_URI="https://example.com/superadmin-dashboard/company-mailbox/callback/",
    MICROSOFT_GRAPH_MAILBOX_USER="michael@bowlinglegacy.com",
    STATICFILES_STORAGE="django.contrib.staticfiles.storage.StaticFilesStorage",
)
class LiveFlowTests(TestCase):
    def application_payload(self):
        return {
            "full_name": "New Applicant",
            "phone": "555-0100",
            "email": "applicant@example.com",
            "age": "42",
            "income_source": "Employment",
            "monthly_income": "2500.00",
            "housing_need": "Needs a vacant room this month.",
            "sobriety_acknowledgment": "on",
            "unconditional_regard_acknowledgment": "on",
        }

    def test_application_from_property_page_keeps_property_assignment(self):
        property_obj = Property.objects.create(name="Painted Lady Inn")

        response = self.client.post(
            f"{reverse('apply')}?property={property_obj.id}",
            self.application_payload(),
        )

        self.assertEqual(response.status_code, 302)

        application = HousingApplication.objects.get(email="applicant@example.com")
        self.assertEqual(application.property, property_obj)

    def test_public_privacy_and_terms_pages_render(self):
        privacy_response = self.client.get(reverse("privacy_policy"))
        terms_response = self.client.get(reverse("terms_of_service"))

        self.assertContains(privacy_response, "does not sell, rent, or share mobile phone numbers")
        self.assertContains(terms_response, "Reply STOP to opt out")

    def test_application_sms_opt_in_records_consent_timestamp(self):
        property_obj = Property.objects.create(name="SMS Consent Property")
        payload = self.application_payload()
        payload["sms_opted_in"] = "on"

        response = self.client.post(
            f"{reverse('apply')}?property={property_obj.id}",
            payload,
        )

        self.assertEqual(response.status_code, 302)
        application = HousingApplication.objects.get(email="applicant@example.com")
        self.assertTrue(application.sms_opted_in)
        self.assertEqual(application.communication_preference, "sms")
        self.assertIsNotNone(application.sms_opted_in_at)

    def test_application_inherits_property_fee_and_background_requirements(self):
        property_obj = Property.objects.create(
            name="Fee Property",
            charges_application_fee=True,
            application_fee_amount=Decimal("35.00"),
            requires_background_check=True,
            background_check_fee_amount=Decimal("45.00"),
        )

        response = self.client.post(
            f"{reverse('apply')}?property={property_obj.id}",
            self.application_payload(),
        )

        self.assertEqual(response.status_code, 302)
        application = HousingApplication.objects.get(email="applicant@example.com")
        self.assertEqual(application.application_fee_amount, Decimal("35.00"))
        self.assertTrue(application.background_check_required)
        self.assertEqual(application.background_check_fee_amount, Decimal("45.00"))
        self.assertEqual(application.background_check_status, "pending")

    def test_application_fee_payment_updates_fee_balance(self):
        application = HousingApplication.objects.create(
            full_name="Fee Applicant",
            phone="555-0100",
            email="fee@example.com",
            age=42,
            application_fee_amount=Decimal("35.00"),
            income_source="Employment",
            monthly_income=Decimal("2500.00"),
            housing_need="Needs housing.",
        )
        payment = Payment.objects.create(
            application=application,
            payment_type="application_fee",
            payment_method="cash",
            amount=Decimal("35.00"),
            status="completed",
        )

        apply_completed_payment_to_balance(payment)

        application.refresh_from_db()
        self.assertEqual(application.application_fee_paid, Decimal("35.00"))

    @patch("main.views.stripe.checkout.Session.create")
    def test_recent_applicant_can_pay_application_fee_from_success_session(self, mock_session_create):
        mock_session_create.return_value = type("StripeSession", (), {
            "id": "cs_test_fee",
            "url": "https://checkout.stripe.test/session",
        })()
        property_obj = Property.objects.create(
            name="Fee Property",
            charges_application_fee=True,
            application_fee_amount=Decimal("35.00"),
        )

        self.client.post(
            f"{reverse('apply')}?property={property_obj.id}",
            self.application_payload(),
        )
        application = HousingApplication.objects.get(email="applicant@example.com")

        response = self.client.get(reverse("pay_by_type", args=[application.id, "application_fee"]))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "https://checkout.stripe.test/session")
        payment = Payment.objects.get(application=application, payment_type="application_fee")
        self.assertEqual(payment.amount, Decimal("35.00"))

    def test_printable_application_includes_full_intake_details(self):
        application = HousingApplication.objects.create(
            full_name="Detailed Applicant",
            phone="555-0100",
            email="detailed@example.com",
            age=42,
            current_address="123 Current Street",
            current_address_length="Two years",
            previous_address_1="Shared housing in Salem",
            previous_address_1_length="Needed stable sober housing",
            income_source="Employment and benefits",
            monthly_income=Decimal("2500.00"),
            employer_name="Local Employer",
            employment_length="18 months",
            previous_evictions="No evictions, one late payment history note.",
            in_recovery=True,
            drug_of_choice="Needs recovery-friendly support.",
            on_parole=True,
            parole_officer_name="Officer Smith",
            parole_officer_phone="555-0199",
            felony_history="Applicant disclosed past conviction context.",
            odoc_time_served=True,
            reference_1_name="Reference One",
            reference_1_phone="555-0111",
            reference_1_relationship="Case manager",
            reference_2_name="Reference Two",
            reference_2_phone="555-0222",
            reference_2_relationship="Employer",
            housing_need="Needs a vacant room this month.",
            sobriety_acknowledgment=True,
            unconditional_regard_acknowledgment=True,
        )

        response = self.client.get(reverse("application_detail", args=[application.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Shared housing in Salem")
        self.assertContains(response, "No evictions, one late payment history note.")
        self.assertContains(response, "Employment and benefits")
        self.assertContains(response, "Officer Smith")
        self.assertContains(response, "Reference One")
        self.assertContains(response, "Needs a vacant room this month.")

    def test_invite_code_allows_resident_to_create_account_and_pay(self):
        temp_user = User.objects.create_user(
            username="new-applicant-1",
            email="applicant@example.com",
            password=None,
            role="tenant",
        )
        temp_user.refresh_invite_code()
        application = HousingApplication.objects.create(
            user=temp_user,
            full_name="New Applicant",
            phone="555-0100",
            email="applicant@example.com",
            age=42,
            income_source="Employment",
            monthly_income=Decimal("2500.00"),
            housing_need="Needs a room.",
            balance=Decimal("900.00"),
        )

        response = self.client.post(reverse("enter_invite_code"), {
            "invite_code": temp_user.invite_code,
        })

        self.assertRedirects(response, reverse("signup"))

        setup_page = self.client.get(reverse("signup"))
        self.assertContains(setup_page, "Show password while I check it")
        self.assertContains(setup_page, "show-passwords")

        response = self.client.post(reverse("signup"), {
            "username": "resident",
            "email": "applicant@example.com",
            "password1": "StrongPass123!",
            "password2": "StrongPass123!",
        })

        self.assertRedirects(response, reverse("tenant_dashboard"))

        application.refresh_from_db()
        self.assertEqual(application.user.username, "resident")
        self.assertFalse(User.objects.filter(id=temp_user.id).exists())

    def test_invite_code_expires_after_30_minutes(self):
        temp_user = User.objects.create_user(
            username="expired-applicant",
            email="expired@example.com",
            password=None,
            role="tenant",
        )
        temp_user.refresh_invite_code()
        temp_user.invite_code_created_at = timezone.now() - timezone.timedelta(minutes=31)
        temp_user.save(update_fields=["invite_code_created_at"])
        HousingApplication.objects.create(
            user=temp_user,
            full_name="Expired Applicant",
            phone="555-0100",
            email="expired@example.com",
            age=42,
            income_source="Employment",
            monthly_income=Decimal("2500.00"),
            housing_need="Needs a room.",
        )

        response = self.client.post(reverse("enter_invite_code"), {
            "invite_code": temp_user.invite_code,
        })

        self.assertRedirects(response, reverse("request_invite_code"))

    def test_property_owner_invite_code_creates_owner_login(self):
        temp_user = User.objects.create_user(
            username="pending-owner",
            email="new-owner@example.com",
            password=None,
            role="property_owner",
        )
        temp_user.refresh_invite_code()
        intake = PropertyOwnerIntake.objects.create(
            full_name="New Owner",
            email="new-owner@example.com",
            phone="555-0130",
            user=temp_user,
            status="invited",
        )

        response = self.client.post(reverse("enter_invite_code"), {"invite_code": temp_user.invite_code})
        self.assertRedirects(response, reverse("signup"))

        response = self.client.post(reverse("signup"), {
            "username": "new-owner",
            "email": "new-owner@example.com",
            "password1": "StrongPass123!",
            "password2": "StrongPass123!",
        })

        self.assertRedirects(response, reverse("property_owner_dashboard"))
        intake.refresh_from_db()
        self.assertEqual(intake.user.username, "new-owner")
        self.assertEqual(intake.status, "registered")
        self.assertFalse(User.objects.filter(id=temp_user.id).exists())

    def test_landlord_invite_code_creates_staff_landlord_login(self):
        temp_user = User.objects.create_user(
            username="pending-landlord",
            email="new-landlord@example.com",
            password=None,
            role="landlord",
            is_staff=True,
        )
        temp_user.refresh_invite_code()
        intake = LandlordIntake.objects.create(
            full_name="New Landlord",
            email="new-landlord@example.com",
            phone="555-0131",
            user=temp_user,
            status="invited",
        )

        response = self.client.post(reverse("enter_invite_code"), {"invite_code": temp_user.invite_code})
        self.assertRedirects(response, reverse("signup"))

        response = self.client.post(reverse("signup"), {
            "full_name": "New Landlord",
            "phone": "555-0131",
            "address": "12 Landlord Lane",
            "username": "new-landlord",
            "email": "new-landlord@example.com",
            "password1": "StrongPass123!",
            "password2": "StrongPass123!",
        })

        self.assertRedirects(response, reverse("landlord_dashboard"))
        intake.refresh_from_db()
        self.assertEqual(intake.user.username, "new-landlord")
        self.assertEqual(intake.full_name, "New Landlord")
        self.assertEqual(intake.phone, "555-0131")
        self.assertEqual(intake.address, "12 Landlord Lane")
        self.assertTrue(intake.user.is_staff)
        self.assertEqual(intake.status, "registered")

    def test_unregistered_user_can_request_replacement_invite_code(self):
        temp_user = User.objects.create_user(
            username="replacement-applicant",
            email="replacement@example.com",
            password=None,
            role="tenant",
        )
        temp_user.refresh_invite_code()
        old_code = temp_user.invite_code
        HousingApplication.objects.create(
            user=temp_user,
            full_name="Replacement Applicant",
            phone="555-0100",
            email="replacement@example.com",
            age=42,
            income_source="Employment",
            monthly_income=Decimal("2500.00"),
            housing_need="Needs a room.",
        )

        response = self.client.post(reverse("request_invite_code"), {
            "email": "replacement@example.com",
        })

        self.assertRedirects(response, reverse("enter_invite_code"))
        temp_user.refresh_from_db()
        self.assertNotEqual(temp_user.invite_code, old_code)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(temp_user.invite_code, mail.outbox[0].body)

    def test_approving_application_sends_invite_email(self):
        staff_user = User.objects.create_user(
            username="staff",
            email="staff@example.com",
            password="StrongPass123!",
            role="landlord",
            is_staff=True,
        )
        property_obj = Property.objects.create(name="Invite Property", landlord_email=staff_user.email)
        application = HousingApplication.objects.create(
            property=property_obj,
            full_name="Email Applicant",
            phone="555-0100",
            email="email-applicant@example.com",
            age=42,
            income_source="Employment",
            monthly_income=Decimal("2500.00"),
            housing_need="Needs a room.",
        )

        self.client.login(username="staff", password="StrongPass123!")

        response = self.client.post(
            f"{reverse('landlord_create_tenant')}?application={application.id}",
            {
                "monthly_rent": "900.00",
                "balance": "900.00",
                "rent_due_day": "1",
                "deposit_required": "450.00",
                "deposit_paid": "0.00",
                "deposit_payment_plan": "ninety_day_plan",
                "utility_monthly": "66.00",
                "utility_balance": "0.00",
                "space_type": "Room",
                "space_label": "3",
            },
        )

        self.assertEqual(response.status_code, 200)

        application.refresh_from_db()
        self.assertIsNotNone(application.user)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(application.user.invite_code, mail.outbox[0].body)
        self.assertIn("https://bowlinglegacy.com/enter-invite-code/", mail.outbox[0].body)
        self.assertEqual(application.deposit_payment_plan, "ninety_day_plan")
        self.assertEqual(
            set(application.signed_documents.values_list("document_type", flat=True)),
            {"lease", "emergency_contact", "painted_lady_acknowledgment"},
        )
        lease = application.signed_documents.get(document_type="lease")
        self.assertEqual(lease.resident_name, "Email Applicant")
        self.assertEqual(lease.monthly_rent, Decimal("900.00"))
        self.assertEqual(lease.security_deposit, Decimal("450.00"))
        self.assertEqual(lease.utility_fee, Decimal("66.00"))
        self.assertEqual(lease.landlord_signature, "Michael Bowling")
        self.assertEqual(lease.deposit_payment_plan, "ninety_day_plan")

    def test_create_tenant_uses_room_rent_setup_over_application_values(self):
        staff_user = User.objects.create_user(
            username="room-setup-staff",
            email="room-setup-staff@example.com",
            password="StrongPass123!",
            role="landlord",
            is_staff=True,
        )
        property_obj = Property.objects.create(name="Room Setup Approval Property", landlord_email=staff_user.email)
        PropertyRoomRent.objects.create(
            property=property_obj,
            room_unit_label="D",
            monthly_rent=Decimal("616.00"),
            rent_due_day=1,
            utility_monthly=Decimal("55.00"),
            deposit_required=Decimal("450.00"),
            deposit_paid=Decimal("0.00"),
        )
        application = HousingApplication.objects.create(
            property=property_obj,
            full_name="Ron Rucker",
            phone="555-0131",
            email="ron-rucker@example.com",
            age=52,
            space_type="Room",
            space_label="D",
            monthly_rent=Decimal("650.00"),
            utility_monthly=Decimal("0.00"),
            deposit_required=Decimal("0.00"),
            income_source="Employment",
            monthly_income=Decimal("2500.00"),
            housing_need="Current resident.",
        )

        self.client.login(username="room-setup-staff", password="StrongPass123!")
        get_response = self.client.get(f"{reverse('landlord_create_tenant')}?application={application.id}")

        self.assertContains(get_response, 'value="616.00"')
        self.assertContains(get_response, 'value="55.00"')

        response = self.client.post(
            f"{reverse('landlord_create_tenant')}?application={application.id}",
            {
                "monthly_rent": "650.00",
                "balance": "650.00",
                "rent_due_day": "17",
                "lease_start_date": "2026-06-01",
                "deposit_required": "0.00",
                "deposit_paid": "0.00",
                "deposit_payment_plan": "paid_in_full",
                "utility_monthly": "0.00",
                "utility_balance": "0.00",
                "space_type": "Room",
                "space_label": "D",
            },
        )

        self.assertEqual(response.status_code, 200)
        application.refresh_from_db()
        self.assertEqual(application.monthly_rent, Decimal("616.00"))
        self.assertEqual(application.balance, Decimal("616.00"))
        self.assertEqual(application.utility_monthly, Decimal("55.00"))
        self.assertEqual(application.utility_balance, Decimal("55.00"))
        self.assertEqual(application.deposit_required, Decimal("450.00"))
        self.assertEqual(application.deposit_paid, Decimal("0.00"))
        self.assertEqual(application.rent_due_day, 1)

    def test_approving_application_prorates_move_in_rent_and_utilities(self):
        staff_user = User.objects.create_user(
            username="prorate-staff",
            email="prorate-staff@example.com",
            password="StrongPass123!",
            role="landlord",
            is_staff=True,
        )
        property_obj = Property.objects.create(name="Prorate Property", landlord_email=staff_user.email)
        application = HousingApplication.objects.create(
            property=property_obj,
            full_name="Prorated Applicant",
            phone="555-0130",
            email="prorated-applicant@example.com",
            age=42,
            income_source="Employment",
            monthly_income=Decimal("2500.00"),
            housing_need="Needs a room.",
        )

        self.client.login(username="prorate-staff", password="StrongPass123!")

        response = self.client.post(
            f"{reverse('landlord_create_tenant')}?application={application.id}",
            {
                "monthly_rent": "650.00",
                "balance": "650.00",
                "rent_due_day": "1",
                "lease_start_date": "2026-05-27",
                "deposit_required": "450.00",
                "deposit_paid": "450.00",
                "deposit_payment_plan": "paid_in_full",
                "utility_monthly": "55.00",
                "utility_balance": "55.00",
                "space_type": "Room",
                "space_label": "H",
            },
        )

        self.assertEqual(response.status_code, 200)
        application.refresh_from_db()
        self.assertEqual(application.monthly_rent, Decimal("650.00"))
        self.assertEqual(application.utility_monthly, Decimal("55.00"))
        self.assertEqual(application.move_in_rent_charge, Decimal("104.84"))
        self.assertEqual(application.balance, Decimal("104.84"))
        self.assertEqual(application.move_in_utility_charge, Decimal("8.87"))
        self.assertEqual(application.utility_balance, Decimal("8.87"))
        self.assertEqual(application.deposit_required, Decimal("450.00"))
        self.assertEqual(application.deposit_paid, Decimal("450.00"))

    def test_prorated_monthly_charge_uses_remaining_calendar_days(self):
        self.assertEqual(prorated_monthly_charge(Decimal("650.00"), date(2026, 5, 27)), Decimal("104.84"))
        self.assertEqual(prorated_monthly_charge(Decimal("55.00"), date(2026, 5, 27)), Decimal("8.87"))

    @patch("main.views.stripe.checkout.Session.create")
    def test_resident_can_start_own_rent_payment(self, create_session):
        create_session.return_value.id = "cs_test_123"
        create_session.return_value.url = "https://checkout.stripe.test/session"

        user = User.objects.create_user(
            username="resident",
            email="resident@example.com",
            password="StrongPass123!",
            role="tenant",
        )
        application = HousingApplication.objects.create(
            user=user,
            full_name="Resident",
            phone="555-0101",
            email="resident@example.com",
            age=50,
            income_source="Employment",
            monthly_income=Decimal("3000.00"),
            housing_need="Current resident.",
            balance=Decimal("900.00"),
        )

        self.client.login(username="resident", password="StrongPass123!")

        response = self.client.get(reverse("pay_by_type", args=[application.id, "rent"]))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "https://checkout.stripe.test/session")
        create_session.assert_called_once()
        self.assertEqual(
            create_session.call_args.kwargs["payment_method_types"],
            ["card", "cashapp"],
        )
        self.assertEqual(Payment.objects.filter(application=application, status="pending").count(), 1)

    def test_resident_cannot_pay_another_resident_account(self):
        user = User.objects.create_user(
            username="resident",
            email="resident@example.com",
            password="StrongPass123!",
            role="tenant",
        )
        other_user = User.objects.create_user(
            username="other",
            email="other@example.com",
            password="StrongPass123!",
            role="tenant",
        )
        HousingApplication.objects.create(
            user=user,
            full_name="Resident",
            phone="555-0101",
            email="resident@example.com",
            age=50,
            income_source="Employment",
            monthly_income=Decimal("3000.00"),
            housing_need="Current resident.",
            balance=Decimal("900.00"),
        )
        other_application = HousingApplication.objects.create(
            user=other_user,
            full_name="Other Resident",
            phone="555-0102",
            email="other@example.com",
            age=51,
            income_source="Employment",
            monthly_income=Decimal("3000.00"),
            housing_need="Current resident.",
            balance=Decimal("900.00"),
        )

        self.client.login(username="resident", password="StrongPass123!")

        response = self.client.get(reverse("pay_by_type", args=[other_application.id, "rent"]))

        self.assertEqual(response.status_code, 403)

    def test_staff_can_record_manual_bank_transfer_rent_payment(self):
        staff_user = User.objects.create_user(
            username="staff",
            email="staff@example.com",
            password="StrongPass123!",
            role="landlord",
            is_staff=True,
        )
        property_obj = Property.objects.create(name="Manual Transfer Property", landlord_email=staff_user.email)
        application = HousingApplication.objects.create(
            property=property_obj,
            full_name="Manual Pay Resident",
            phone="555-0103",
            email="manual@example.com",
            age=44,
            income_source="Employment",
            monthly_income=Decimal("3000.00"),
            housing_need="Current resident.",
            balance=Decimal("900.00"),
        )

        self.client.login(username="staff", password="StrongPass123!")

        response = self.client.post(reverse("record_manual_payment"), {
            "application": application.id,
            "payment_type": "rent",
            "payment_method": "bank_transfer",
            "amount": "250.00",
            "reference_number": "BANK-123",
            "description": "Same-bank transfer",
            "notes": "Confirmed in bank portal.",
        })

        payment = Payment.objects.get(application=application)
        self.assertRedirects(response, reverse("payment_receipt", args=[payment.id]))

        application.refresh_from_db()
        self.assertEqual(application.balance, Decimal("650.00"))

        self.assertEqual(payment.status, "completed")
        self.assertEqual(payment.payment_method, "bank_transfer")
        self.assertEqual(payment.reference_number, "BANK-123")
        self.assertEqual(payment.recorded_by, staff_user)

        response = self.client.get(reverse("payment_receipt", args=[payment.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Payment Receipt")
        self.assertContains(response, "BANK-123")

    def test_record_payment_prompts_for_property_when_multiple_properties_exist(self):
        staff_user = User.objects.create_user(
            username="payment-picker-staff",
            email="payment-picker@example.com",
            password="StrongPass123!",
            role="landlord",
            is_staff=True,
        )
        first_property = Property.objects.create(name="First Payment Property", landlord_email=staff_user.email)
        second_property = Property.objects.create(name="Second Payment Property", landlord_email=staff_user.email)
        first_user = User.objects.create_user(username="first-payment-resident", password="StrongPass123!", role="tenant")
        second_user = User.objects.create_user(username="second-payment-resident", password="StrongPass123!", role="tenant")
        first_resident = HousingApplication.objects.create(
            property=first_property,
            user=first_user,
            full_name="First Payment Resident",
            phone="555-0130",
            email="first-payment@example.com",
            age=44,
            income_source="Employment",
            monthly_income=Decimal("3000.00"),
            housing_need="Current resident.",
        )
        second_resident = HousingApplication.objects.create(
            property=second_property,
            user=second_user,
            full_name="Second Payment Resident",
            phone="555-0131",
            email="second-payment@example.com",
            age=45,
            income_source="Employment",
            monthly_income=Decimal("3000.00"),
            housing_need="Current resident.",
        )

        self.client.login(username="payment-picker-staff", password="StrongPass123!")
        response = self.client.get(reverse("record_manual_payment"))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["show_property_picker"])
        self.assertContains(response, "First Payment Property")
        self.assertContains(response, "Second Payment Property")

        property_response = self.client.get(reverse("record_manual_payment_property", args=[second_property.id]))
        choices = list(property_response.context["form"].fields["application"].queryset)

        self.assertFalse(property_response.context["show_property_picker"])
        self.assertEqual(property_response.context["selected_property"], second_property)
        self.assertIn(second_resident, choices)
        self.assertNotIn(first_resident, choices)

    def test_single_property_record_payment_opens_directly(self):
        staff_user = User.objects.create_user(
            username="single-payment-staff",
            email="single-payment@example.com",
            password="StrongPass123!",
            role="landlord",
            is_staff=True,
        )
        property_obj = Property.objects.create(name="Single Payment Property", landlord_email=staff_user.email)
        resident_user = User.objects.create_user(username="single-payment-resident", password="StrongPass123!", role="tenant")
        resident = HousingApplication.objects.create(
            property=property_obj,
            user=resident_user,
            full_name="Single Payment Resident",
            phone="555-0132",
            email="single-payment-resident@example.com",
            age=46,
            income_source="Employment",
            monthly_income=Decimal("3000.00"),
            housing_need="Current resident.",
        )

        self.client.login(username="single-payment-staff", password="StrongPass123!")
        response = self.client.get(reverse("record_manual_payment"))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["show_property_picker"])
        self.assertEqual(response.context["selected_property"], property_obj)
        self.assertIn(resident, list(response.context["form"].fields["application"].queryset))

    def test_manual_payment_can_apply_to_future_rent_month(self):
        staff_user = User.objects.create_user(
            username="future-rent-staff",
            email="future-rent-staff@example.com",
            password="StrongPass123!",
            role="landlord",
            is_staff=True,
        )
        property_obj = Property.objects.create(name="Future Rent Property", landlord_email=staff_user.email)
        application = HousingApplication.objects.create(
            property=property_obj,
            full_name="Future Rent Resident",
            phone="555-0201",
            email="future-rent@example.com",
            age=44,
            income_source="Employment",
            monthly_income=Decimal("3000.00"),
            housing_need="Current resident.",
            balance=Decimal("650.00"),
        )

        self.client.login(username="future-rent-staff", password="StrongPass123!")
        response = self.client.post(reverse("record_manual_payment"), {
            "application": application.id,
            "payment_type": "rent",
            "payment_method": "cash",
            "amount": "650.00",
            "service_month": "2026-06",
            "months_covered": "1",
            "reference_number": "CASH-JUNE",
            "description": "June rent paid in May",
            "notes": "",
        })

        payment = Payment.objects.get(application=application)
        self.assertRedirects(response, reverse("payment_receipt", args=[payment.id]))
        self.assertEqual(payment.service_month, date(2026, 6, 1))
        self.assertEqual(payment.months_covered, 1)
        self.assertEqual(payment_amount_for_month([payment], 2026, 5, ["rent"]), Decimal("0.00"))
        self.assertEqual(payment_amount_for_month([payment], 2026, 6, ["rent"]), Decimal("650.00"))

        payment_log = self.client.get(reverse("payment_log"))
        self.assertContains(payment_log, "June 2026")
        self.assertContains(payment_log, "Unit")
        self.assertContains(payment_log, "Date/Time")
        self.assertContains(payment_log, "Rent Balance")
        self.assertNotContains(payment_log, "Room / Unit")
        self.assertNotContains(payment_log, "Date / Time Paid")
        self.assertNotContains(payment_log, "Rent Balance Owed")
        self.assertNotContains(payment_log, "<th>Description</th>", html=True)
        self.assertNotContains(payment_log, "<th>Reference</th>", html=True)
        self.assertNotContains(payment_log, "CASH-JUNE")

    def test_multi_month_payment_is_allocated_across_reporting_months(self):
        application = HousingApplication.objects.create(
            full_name="Multi Month Resident",
            phone="555-0202",
            email="multi-month@example.com",
            age=44,
            income_source="Employment",
            monthly_income=Decimal("3000.00"),
            housing_need="Current resident.",
        )
        payment = Payment.objects.create(
            application=application,
            payment_type="rent",
            payment_method="check",
            amount=Decimal("1300.00"),
            status="completed",
            service_month=date(2026, 6, 1),
            months_covered=2,
        )

        self.assertEqual(payment_amount_for_month([payment], 2026, 6, ["rent"]), Decimal("650.00"))
        self.assertEqual(payment_amount_for_month([payment], 2026, 7, ["rent"]), Decimal("650.00"))
        self.assertEqual(payment_amount_for_month([payment], 2026, 8, ["rent"]), Decimal("0.00"))

    def test_manual_payment_requires_payment_type_selection(self):
        staff_user = User.objects.create_user(
            username="blank-payment-type-staff",
            email="blank-payment-type-staff@example.com",
            password="StrongPass123!",
            role="landlord",
            is_staff=True,
        )
        property_obj = Property.objects.create(name="Blank Type Property", landlord_email=staff_user.email)
        application = HousingApplication.objects.create(
            property=property_obj,
            full_name="Blank Type Resident",
            phone="555-0119",
            email="blank-type@example.com",
            age=42,
            income_source="Employment",
            monthly_income=Decimal("3000.00"),
            housing_need="Current resident.",
            balance=Decimal("100.00"),
        )

        self.client.login(username="blank-payment-type-staff", password="StrongPass123!")
        response = self.client.post(reverse("record_manual_payment"), {
            "application": application.id,
            "payment_type": "",
            "payment_method": "cash",
            "amount": "100.00",
        })

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Payment.objects.filter(application=application).exists())
        self.assertContains(response, "This field is required")

    def test_staff_can_correct_manual_payment_type_and_recalculate_balances(self):
        staff_user = User.objects.create_user(
            username="correct-payment-staff",
            email="correct-payment-staff@example.com",
            password="StrongPass123!",
            role="landlord",
            is_staff=True,
        )
        property_obj = Property.objects.create(name="Correct Payment Property", landlord_email=staff_user.email)
        application = HousingApplication.objects.create(
            property=property_obj,
            full_name="Correct Payment Resident",
            phone="555-0120",
            email="correct-payment@example.com",
            age=42,
            income_source="Employment",
            monthly_income=Decimal("3000.00"),
            housing_need="Current resident.",
            monthly_rent=Decimal("104.84"),
            balance=Decimal("104.84"),
            utility_monthly=Decimal("8.87"),
            utility_balance=Decimal("8.87"),
            deposit_required=Decimal("450.00"),
            deposit_paid=Decimal("0.00"),
            move_in_rent_charge=Decimal("104.84"),
            move_in_utility_charge=Decimal("8.87"),
        )
        payment = Payment.objects.create(
            application=application,
            payment_type="rent",
            payment_method="cash",
            amount=Decimal("450.00"),
            status="completed",
            recorded_by=staff_user,
        )
        apply_completed_payment_to_balance(payment)
        application.refresh_from_db()
        self.assertEqual(application.balance, Decimal("0.00"))
        self.assertEqual(application.deposit_paid, Decimal("0.00"))

        self.client.login(username="correct-payment-staff", password="StrongPass123!")
        response = self.client.post(reverse("edit_manual_payment", args=[payment.id]), {
            "application": application.id,
            "payment_type": "deposit",
            "payment_method": "cash",
            "amount": "450.00",
            "description": "Corrected to deposit",
            "reference_number": "",
            "notes": "",
        })

        self.assertRedirects(response, reverse("payment_receipt", args=[payment.id]))
        payment.refresh_from_db()
        application.refresh_from_db()
        self.assertEqual(payment.payment_type, "deposit")
        self.assertEqual(application.balance, Decimal("104.84"))
        self.assertEqual(application.utility_balance, Decimal("8.87"))
        self.assertEqual(application.deposit_paid, Decimal("450.00"))

    def test_staff_can_record_manual_cashapp_deposit_payment(self):
        staff_user = User.objects.create_user(
            username="staff",
            email="staff@example.com",
            password="StrongPass123!",
            role="landlord",
            is_staff=True,
        )
        property_obj = Property.objects.create(name="Cash App Property", landlord_email=staff_user.email)
        application = HousingApplication.objects.create(
            property=property_obj,
            full_name="Cash App Resident",
            phone="555-0104",
            email="cashapp@example.com",
            age=45,
            income_source="Employment",
            monthly_income=Decimal("3000.00"),
            housing_need="Current resident.",
            deposit_required=Decimal("450.00"),
            deposit_paid=Decimal("100.00"),
        )

        self.client.login(username="staff", password="StrongPass123!")

        response = self.client.post(reverse("record_manual_payment"), {
            "application": application.id,
            "payment_type": "deposit",
            "payment_method": "cashapp",
            "amount": "200.00",
            "reference_number": "CashApp $resident",
            "description": "Cash App deposit payment",
        })

        payment = Payment.objects.get(application=application)
        self.assertRedirects(response, reverse("payment_receipt", args=[payment.id]))

        application.refresh_from_db()
        self.assertEqual(application.deposit_paid, Decimal("300.00"))

        self.assertEqual(payment.payment_method, "cashapp")
        self.assertEqual(payment.recorded_by, staff_user)

    def test_landlord_dashboard_highlights_new_items(self):
        staff_user = User.objects.create_user(
            username="staff",
            email="staff@example.com",
            password="StrongPass123!",
            role="landlord",
            is_staff=True,
        )
        property_obj = Property.objects.create(name="Attention Property", landlord_email=staff_user.email)
        application = HousingApplication.objects.create(
            property=property_obj,
            full_name="New Queue Resident",
            phone="555-0105",
            email="queue@example.com",
            age=46,
            income_source="Employment",
            monthly_income=Decimal("3000.00"),
            housing_need="Needs review.",
        )
        ResidentMessage.objects.create(
            application=application,
            message_type="maintenance",
            subject="New request",
            message="Please review.",
            status="submitted",
        )
        ApplicantDocument.objects.create(
            application=application,
            document_type="id",
            name="Uploaded ID",
            file="applicant_documents/id.pdf",
            status="uploaded",
            landlord_notified=False,
        )

        self.client.login(username="staff", password="StrongPass123!")

        response = self.client.get(reverse("landlord_attention"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Needs Attention")
        self.assertContains(response, "New Queue Resident")
        self.assertContains(response, "New request")
        self.assertContains(response, "Uploaded ID")
        self.assertContains(response, "Mark Reviewed")

    def test_landlord_attention_collapses_duplicate_profile_setups_and_applications(self):
        staff_user = User.objects.create_user(
            username="dedupe-staff",
            email="dedupe-staff@example.com",
            password="StrongPass123!",
            role="landlord",
            is_staff=True,
        )
        property_obj = Property.objects.create(name="Dedupe Property", landlord_email=staff_user.email)

        HousingApplication.objects.create(
            property=property_obj,
            full_name="Duplicate Applicant",
            phone="555-0301",
            email="duplicate-applicant@example.com",
            age=41,
            income_source="Employment",
            monthly_income=Decimal("3000.00"),
            housing_need="First application.",
        )
        HousingApplication.objects.create(
            property=property_obj,
            full_name="Duplicate Applicant",
            phone="555-0301",
            email="duplicate-applicant@example.com",
            age=41,
            income_source="Employment",
            monthly_income=Decimal("3000.00"),
            housing_need="Second application.",
        )

        ExistingResidentIntake.objects.create(
            property=property_obj,
            first_name="Mike",
            last_name="Dudley",
            email="mike@example.com",
            phone="555-0302",
            room_unit_label="J",
        )
        ExistingResidentIntake.objects.create(
            property=property_obj,
            first_name="Mike",
            last_name="Dudley",
            email="mike@example.com",
            phone="555-0302",
            room_unit_label="Room J",
        )

        self.client.login(username="dedupe-staff", password="StrongPass123!")
        response = self.client.get(reverse("landlord_attention"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["new_applications"]), 1)
        self.assertEqual(len(response.context["existing_resident_intakes"]), 1)
        self.assertContains(response, "2 duplicate applications")
        self.assertContains(response, "2 duplicate setup attempts")

    def test_landlord_can_reply_to_scoped_resident_message(self):
        landlord = User.objects.create_user(
            username="reply-landlord",
            email="reply-landlord@example.com",
            password="StrongPass123!",
            role="landlord",
            is_staff=True,
        )
        property_obj = Property.objects.create(name="Reply Property", landlord_email=landlord.email)
        application = HousingApplication.objects.create(
            property=property_obj,
            full_name="Reply Resident",
            phone="555-0106",
            email="reply-resident@example.com",
            age=46,
            income_source="Employment",
            monthly_income=Decimal("3000.00"),
            housing_need="Needs review.",
        )
        resident_message = ResidentMessage.objects.create(
            application=application,
            message_type="maintenance",
            subject="Repair request",
            message="Please fix this.",
            status="submitted",
        )

        self.client.login(username="reply-landlord", password="StrongPass123!")
        response = self.client.post(reverse("landlord_message_detail", args=[resident_message.id]), {
            "reply_body": "I will check this today.",
        })

        self.assertRedirects(response, reverse("landlord_message_detail", args=[resident_message.id]))
        reply = ResidentMessageReply.objects.get(message=resident_message)
        self.assertEqual(reply.sender, landlord)
        self.assertEqual(reply.body, "I will check this today.")
        resident_message.refresh_from_db()
        self.assertEqual(resident_message.status, "reviewed")
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["reply-resident@example.com"])
        self.assertIn("new secure reply", mail.outbox[0].body.lower())
        self.assertIn(reverse("resident_requests"), mail.outbox[0].body)
        self.assertIn("ask for your login", mail.outbox[0].body)
        sms_log = SmsMessageLog.objects.get(resident_message=resident_message)
        self.assertEqual(sms_log.status, "skipped_no_consent")
        self.assertIn(reverse("resident_requests"), sms_log.body)

    def test_landlord_cannot_reply_to_other_property_message(self):
        landlord = User.objects.create_user(
            username="blocked-reply-landlord",
            email="blocked-reply-landlord@example.com",
            password="StrongPass123!",
            role="landlord",
            is_staff=True,
        )
        other_property = Property.objects.create(name="Other Reply Property", landlord_email="other@example.com")
        application = HousingApplication.objects.create(
            property=other_property,
            full_name="Other Reply Resident",
            phone="555-0107",
            email="other-reply-resident@example.com",
            age=46,
            income_source="Employment",
            monthly_income=Decimal("3000.00"),
            housing_need="Needs review.",
        )
        resident_message = ResidentMessage.objects.create(
            application=application,
            subject="Other request",
            message="Private message.",
        )

        self.client.login(username="blocked-reply-landlord", password="StrongPass123!")
        response = self.client.post(reverse("landlord_message_detail", args=[resident_message.id]), {
            "reply_body": "Should not send.",
        })

        self.assertEqual(response.status_code, 404)
        self.assertFalse(ResidentMessageReply.objects.filter(message=resident_message).exists())

    def test_landlord_group_message_only_targets_accessible_property_residents(self):
        landlord = User.objects.create_user(
            username="group-message-landlord",
            email="group-message-landlord@example.com",
            password="StrongPass123!",
            role="landlord",
            is_staff=True,
        )
        resident_user = User.objects.create_user(username="group-resident", password="StrongPass123!", role="tenant")
        other_resident_user = User.objects.create_user(username="other-group-resident", password="StrongPass123!", role="tenant")
        property_obj = Property.objects.create(name="Group Message Property", landlord_email=landlord.email)
        other_property = Property.objects.create(name="Other Group Message Property", landlord_email="other@example.com")
        application = HousingApplication.objects.create(
            property=property_obj,
            user=resident_user,
            full_name="Group Resident",
            phone="555-0108",
            email="group-resident@example.com",
            age=46,
            income_source="Employment",
            monthly_income=Decimal("3000.00"),
            housing_need="Current resident.",
        )
        other_application = HousingApplication.objects.create(
            property=other_property,
            user=other_resident_user,
            full_name="Other Group Resident",
            phone="555-0109",
            email="other-group-resident@example.com",
            age=46,
            income_source="Employment",
            monthly_income=Decimal("3000.00"),
            housing_need="Current resident.",
        )

        self.client.login(username="group-message-landlord", password="StrongPass123!")
        response = self.client.post(reverse("group_resident_message"), {
            "property_id": "all",
            "delivery_method": "portal",
            "subject": "Building notice",
            "message": "This is a secure group notice.",
        })

        self.assertRedirects(response, reverse("group_resident_message"))
        self.assertTrue(ResidentMessage.objects.filter(application=application, subject="Building notice").exists())
        self.assertFalse(ResidentMessage.objects.filter(application=other_application, subject="Building notice").exists())
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["group-resident@example.com"])
        self.assertIn(reverse("resident_requests"), mail.outbox[0].body)

    def test_landlord_can_set_rent_for_resident_without_portal_login(self):
        landlord = User.objects.create_user(
            username="rent-setup-landlord",
            email="rent-setup-landlord@example.com",
            password="StrongPass123!",
            role="landlord",
            is_staff=True,
        )
        property_obj = Property.objects.create(name="Rent Setup Property", landlord_email=landlord.email)
        resident = HousingApplication.objects.create(
            property=property_obj,
            full_name="Rent Setup Resident",
            phone="555-0112",
            email="rent-setup@example.com",
            age=46,
            income_source="Employment",
            monthly_income=Decimal("3000.00"),
            housing_need="Current resident.",
            monthly_rent=Decimal("0.00"),
            balance=Decimal("0.00"),
            utility_monthly=Decimal("0.00"),
            utility_balance=Decimal("0.00"),
        )

        self.client.login(username="rent-setup-landlord", password="StrongPass123!")
        response = self.client.post(reverse("landlord_rent_setup"), {
            f"resident_{resident.id}_monthly_rent": "575.00",
            f"resident_{resident.id}_balance": "575.00",
            f"resident_{resident.id}_rent_due_day": "5",
            f"resident_{resident.id}_utility_monthly": "66.00",
            f"resident_{resident.id}_utility_balance": "66.00",
        })

        self.assertRedirects(response, reverse("landlord_rent_setup"))
        resident.refresh_from_db()
        self.assertEqual(resident.monthly_rent, Decimal("575.00"))
        self.assertEqual(resident.balance, Decimal("575.00"))
        self.assertEqual(resident.rent_due_day, 5)
        self.assertEqual(resident.utility_monthly, Decimal("66.00"))
        self.assertEqual(resident.utility_balance, Decimal("66.00"))
        self.assertTrue(RentHistory.objects.filter(application=resident, rent_amount=Decimal("575.00")).exists())

    def test_landlord_can_set_rent_by_room_letter_before_profile_exists(self):
        landlord = User.objects.create_user(
            username="room-rent-landlord",
            email="room-rent-landlord@example.com",
            password="StrongPass123!",
            role="landlord",
            is_staff=True,
        )
        property_obj = Property.objects.create(name="Room Rent Property", landlord_email=landlord.email)
        CurrentResidentRosterEntry.objects.create(
            property=property_obj,
            first_name="Grady",
            last_name="Brady",
            email="grady@example.com",
            room_unit_label="B",
            uploaded_by=landlord,
        )

        self.client.login(username="room-rent-landlord", password="StrongPass123!")
        response = self.client.post(reverse("landlord_rent_setup"), {
            "room_count": "1",
            "room_0_property_id": str(property_obj.id),
            "room_0_room_unit_label": "B",
            "room_0_monthly_rent": "525.00",
            "room_0_rent_due_day": "3",
            "room_0_utility_monthly": "60.00",
        })

        self.assertRedirects(response, reverse("landlord_rent_setup"))
        room_rent = PropertyRoomRent.objects.get(property=property_obj, room_unit_label="B")
        self.assertEqual(room_rent.monthly_rent, Decimal("525.00"))
        self.assertEqual(room_rent.rent_due_day, 3)
        self.assertEqual(room_rent.utility_monthly, Decimal("60.00"))

    def test_rent_setup_prompts_for_property_when_multiple_properties_exist(self):
        landlord = User.objects.create_user(
            username="multi-rent-setup-landlord",
            email="multi-rent-setup@example.com",
            password="StrongPass123!",
            role="landlord",
            is_staff=True,
        )
        first_property = Property.objects.create(name="First Rent Setup Property", landlord_email=landlord.email)
        second_property = Property.objects.create(name="Second Rent Setup Property", landlord_email=landlord.email)
        PropertyRoomRent.objects.create(property=first_property, room_unit_label="A", monthly_rent=Decimal("500.00"))
        PropertyRoomRent.objects.create(property=second_property, room_unit_label="B", monthly_rent=Decimal("600.00"))

        self.client.login(username="multi-rent-setup-landlord", password="StrongPass123!")
        response = self.client.get(reverse("landlord_rent_setup"))

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["selected_property"])
        self.assertContains(response, "Choose a property before editing rent")
        self.assertContains(response, "First Rent Setup Property")
        self.assertContains(response, "Second Rent Setup Property")

        property_response = self.client.get(reverse("landlord_rent_setup_property", args=[second_property.id]))

        self.assertEqual(property_response.status_code, 200)
        self.assertEqual(property_response.context["selected_property"], second_property)
        self.assertContains(property_response, "Second Rent Setup Property monthly rent setup")
        self.assertContains(property_response, "<strong>B</strong>", html=True)
        self.assertNotContains(property_response, "<strong>A</strong>", html=True)

    def test_single_property_rent_setup_opens_directly(self):
        landlord = User.objects.create_user(
            username="single-rent-setup-landlord",
            email="single-rent-setup@example.com",
            password="StrongPass123!",
            role="landlord",
            is_staff=True,
        )
        property_obj = Property.objects.create(name="Single Rent Setup Property", landlord_email=landlord.email)

        self.client.login(username="single-rent-setup-landlord", password="StrongPass123!")
        response = self.client.get(reverse("landlord_rent_setup"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["selected_property"], property_obj)
        self.assertContains(response, "Single Rent Setup Property monthly rent setup")

    def test_landlord_can_record_deposit_by_room_letter(self):
        landlord = User.objects.create_user(
            username="room-deposit-landlord",
            email="room-deposit-landlord@example.com",
            password="StrongPass123!",
            role="landlord",
            is_staff=True,
        )
        property_obj = Property.objects.create(name="Room Deposit Property", landlord_email=landlord.email)
        resident = HousingApplication.objects.create(
            property=property_obj,
            full_name="Deposit Resident",
            phone="555-0117",
            email="deposit-resident@example.com",
            age=45,
            income_source="Employment",
            monthly_income=Decimal("3000.00"),
            housing_need="Current resident.",
            space_type="Room",
            space_label="D",
            deposit_required=Decimal("0.00"),
            deposit_paid=Decimal("0.00"),
        )

        self.client.login(username="room-deposit-landlord", password="StrongPass123!")
        response = self.client.post(reverse("landlord_rent_setup"), {
            "room_count": "1",
            "room_0_property_id": str(property_obj.id),
            "room_0_room_unit_label": "D",
            "room_0_monthly_rent": "500.00",
            "room_0_rent_due_day": "1",
            "room_0_utility_monthly": "0.00",
            "room_0_deposit_required": "450.00",
            "room_0_deposit_paid": "0.00",
            "apply_room_rents": "on",
            f"resident_{resident.id}_monthly_rent": "0.00",
            f"resident_{resident.id}_balance": "0.00",
            f"resident_{resident.id}_rent_due_day": "1",
            f"resident_{resident.id}_utility_monthly": "0.00",
            f"resident_{resident.id}_utility_balance": "0.00",
            f"resident_{resident.id}_deposit_required": "0.00",
            f"resident_{resident.id}_deposit_paid": "0.00",
        })

        self.assertRedirects(response, reverse("landlord_rent_setup"))
        room_rent = PropertyRoomRent.objects.get(property=property_obj, room_unit_label="D")
        self.assertEqual(room_rent.deposit_required, Decimal("450.00"))
        self.assertEqual(room_rent.deposit_paid, Decimal("0.00"))
        resident.refresh_from_db()
        self.assertEqual(resident.deposit_required, Decimal("450.00"))
        self.assertEqual(resident.deposit_paid, Decimal("0.00"))

    def test_landlord_can_transfer_resident_room_and_apply_room_settings(self):
        landlord = User.objects.create_user(
            username="room-transfer-landlord",
            email="room-transfer-landlord@example.com",
            password="StrongPass123!",
            role="landlord",
            is_staff=True,
        )
        property_obj = Property.objects.create(name="Room Transfer Property", landlord_email=landlord.email)
        resident = HousingApplication.objects.create(
            property=property_obj,
            full_name="Room Transfer Resident",
            phone="555-0450",
            email="transfer@example.com",
            age=50,
            space_type="Room",
            space_label="A",
            monthly_rent=Decimal("500.00"),
            balance=Decimal("500.00"),
            income_source="Employment",
            monthly_income=Decimal("3000.00"),
            housing_need="Current resident.",
        )
        PropertyRoomRent.objects.create(
            property=property_obj,
            room_unit_label="B",
            monthly_rent=Decimal("650.00"),
            rent_due_day=3,
            utility_monthly=Decimal("75.00"),
            deposit_required=Decimal("450.00"),
            deposit_paid=Decimal("0.00"),
        )

        self.client.login(username="room-transfer-landlord", password="StrongPass123!")
        response = self.client.post(reverse("transfer_resident_room", args=[resident.id]), {
            "space_type": "Room",
            "space_label": "B",
            "apply_room_rent": "on",
            "notes": "Resident requested larger room.",
        })

        self.assertRedirects(response, reverse("application_detail", args=[resident.id]))
        resident.refresh_from_db()
        self.assertEqual(resident.space_label, "B")
        self.assertEqual(resident.monthly_rent, Decimal("650.00"))
        self.assertEqual(resident.balance, Decimal("650.00"))
        self.assertEqual(resident.rent_due_day, 3)
        self.assertEqual(resident.utility_monthly, Decimal("75.00"))
        self.assertIn("larger room", resident.additional_notes)
        self.assertTrue(RentHistory.objects.filter(application=resident, rent_amount=Decimal("650.00")).exists())

    def test_landlord_can_archive_moved_out_resident_file(self):
        landlord = User.objects.create_user(
            username="move-out-landlord",
            email="move-out-landlord@example.com",
            password="StrongPass123!",
            role="landlord",
            is_staff=True,
        )
        tenant_user = User.objects.create_user(
            username="move-out-tenant",
            email="move-out-tenant@example.com",
            password="StrongPass123!",
            role="tenant",
        )
        property_obj = Property.objects.create(name="Move Out Property", landlord_email=landlord.email)
        resident = HousingApplication.objects.create(
            property=property_obj,
            user=tenant_user,
            full_name="Move Out Resident",
            phone="555-0550",
            email="move-out@example.com",
            age=50,
            space_type="Room",
            space_label="C",
            monthly_rent=Decimal("500.00"),
            balance=Decimal("0.00"),
            income_source="Employment",
            monthly_income=Decimal("3000.00"),
            housing_need="Current resident.",
        )
        Payment.objects.create(application=resident, payment_type="rent", amount=Decimal("500.00"), status="completed")
        ResidentMessage.objects.create(application=resident, subject="Move out note", message="History remains.")
        CurrentResidentRosterEntry.objects.create(
            property=property_obj,
            first_name="Move Out",
            last_name="Resident",
            room_unit_label="C",
            is_active=True,
        )
        PropertyRoomRent.objects.create(property=property_obj, room_unit_label="C", monthly_rent=Decimal("500.00"))

        self.client.login(username="move-out-landlord", password="StrongPass123!")
        response = self.client.post(reverse("archive_resident_move_out", args=[resident.id]), {
            "move_out_date": "2026-06-12",
            "archive_notes": "Keys returned.",
        })

        self.assertRedirects(response, reverse("landlord_resident_files"))
        resident.refresh_from_db()
        tenant_user.refresh_from_db()
        self.assertEqual(resident.resident_file_status, "archived")
        self.assertEqual(resident.move_out_date, date(2026, 6, 12))
        self.assertIn("Keys returned", resident.archive_notes)
        self.assertFalse(tenant_user.is_active)
        self.assertTrue(Payment.objects.filter(application=resident).exists())
        self.assertTrue(ResidentMessage.objects.filter(application=resident).exists())
        self.assertTrue(PropertyRoomRent.objects.filter(property=property_obj, room_unit_label="C").exists())
        self.assertFalse(CurrentResidentRosterEntry.objects.get(property=property_obj, room_unit_label="C").is_active)

        resident_files = self.client.get(reverse("landlord_resident_files"))
        self.assertNotContains(resident_files, "Move Out / Archive")
        self.assertContains(resident_files, "Archived Resident Files")
        self.assertContains(resident_files, "Open Archive")

    def test_landlord_can_upload_and_review_tenant_file_packet(self):
        landlord = User.objects.create_user(
            username="packet-landlord",
            email="packet-landlord@example.com",
            password="StrongPass123!",
            role="landlord",
            is_staff=True,
        )
        property_obj = Property.objects.create(name="Packet Property", landlord_email=landlord.email)
        resident = HousingApplication.objects.create(
            property=property_obj,
            full_name="Packet Resident",
            phone="555-0660",
            email="packet@example.com",
            age=50,
            space_type="Room",
            space_label="D",
            monthly_rent=Decimal("500.00"),
            income_source="Employment",
            monthly_income=Decimal("3000.00"),
            housing_need="Current resident.",
        )

        self.client.login(username="packet-landlord", password="StrongPass123!")
        response = self.client.post(reverse("tenant_file_packet_upload"), {
            "target_type": "resident",
            "property": str(property_obj.id),
            "application": str(resident.id),
            "unit_label": "",
            "document_type": "lease",
            "name": "Scanned Lease Packet",
            "packet_notes": "Original paper file.",
            "run_ocr": "on",
            "file": SimpleUploadedFile(
                "lease.txt",
                b"Resident: Packet Resident\nUnit: D\nLease date 06/12/2026\n",
                content_type="text/plain",
            ),
        })

        document = ApplicantDocument.objects.get(application=resident, name="Scanned Lease Packet")
        self.assertRedirects(response, reverse("tenant_file_packet_review", args=[document.id]))
        self.assertTrue(document.packet_upload)
        self.assertEqual(document.ocr_status, "extracted")
        self.assertEqual(document.ocr_suggested_unit, "D")

        review_response = self.client.post(reverse("tenant_file_packet_review", args=[document.id]), {"action": "review"})
        self.assertRedirects(review_response, reverse("application_detail", args=[resident.id]))
        document.refresh_from_db()
        self.assertTrue(document.locked)
        self.assertEqual(document.status, "locked")
        self.assertEqual(document.packet_reviewed_by, landlord)

    def test_landlord_can_upload_packet_to_empty_unit_placeholder(self):
        landlord = User.objects.create_user(
            username="unit-packet-landlord",
            email="unit-packet-landlord@example.com",
            password="StrongPass123!",
            role="landlord",
            is_staff=True,
        )
        property_obj = Property.objects.create(name="Unit Packet Property", landlord_email=landlord.email)

        self.client.login(username="unit-packet-landlord", password="StrongPass123!")
        response = self.client.post(reverse("tenant_file_packet_upload"), {
            "target_type": "unit",
            "property": str(property_obj.id),
            "unit_label": "E",
            "document_type": "other",
            "name": "Empty Unit Old File",
            "run_ocr": "",
            "file": SimpleUploadedFile("packet.txt", b"Unit E old paper file", content_type="text/plain"),
        })

        placeholder = HousingApplication.objects.get(property=property_obj, resident_file_status="unit_file", space_label="E")
        document = ApplicantDocument.objects.get(application=placeholder, name="Empty Unit Old File")
        self.assertRedirects(response, reverse("tenant_file_packet_review", args=[document.id]))
        self.assertEqual(placeholder.full_name, "Unit E File")

        resident_files = self.client.get(reverse("landlord_resident_files"))
        self.assertNotContains(resident_files, "Unit E File")

    def test_landlord_can_reassign_unit_packet_to_resident_file(self):
        landlord = User.objects.create_user(
            username="packet-reassign-landlord",
            email="packet-reassign-landlord@example.com",
            password="StrongPass123!",
            role="landlord",
            is_staff=True,
        )
        property_obj = Property.objects.create(name="Packet Reassign Property", landlord_email=landlord.email)
        resident = HousingApplication.objects.create(
            property=property_obj,
            full_name="Assigned Packet Resident",
            phone="555-0770",
            email="assigned-packet@example.com",
            age=50,
            space_type="Room",
            space_label="E",
            monthly_rent=Decimal("500.00"),
            income_source="Employment",
            monthly_income=Decimal("3000.00"),
            housing_need="Current resident.",
        )
        placeholder = HousingApplication.objects.create(
            property=property_obj,
            resident_file_status="unit_file",
            full_name="Unit E File",
            phone="",
            email="",
            age=0,
            space_type="Unit",
            space_label="E",
            income_source="Tenant file packet placeholder",
            monthly_income=Decimal("0.00"),
            housing_need="Empty unit file packet placeholder.",
        )
        document = ApplicantDocument.objects.create(
            application=placeholder,
            document_type="other",
            name="Old Unit Packet",
            file=SimpleUploadedFile("old-packet.txt", b"Unit E old file", content_type="text/plain"),
            packet_upload=True,
            landlord_notified=True,
        )

        self.client.login(username="packet-reassign-landlord", password="StrongPass123!")
        queue_response = self.client.get(reverse("landlord_resident_files"))
        self.assertContains(queue_response, "Tenant File Packets Needing Review")
        self.assertContains(queue_response, "Old Unit Packet")

        response = self.client.post(reverse("tenant_file_packet_review", args=[document.id]), {
            "action": "reassign",
            "application": str(resident.id),
        })

        self.assertRedirects(response, reverse("tenant_file_packet_review", args=[document.id]))
        document.refresh_from_db()
        self.assertEqual(document.application, resident)

        review_response = self.client.post(reverse("tenant_file_packet_review", args=[document.id]), {"action": "review"})
        self.assertRedirects(review_response, reverse("application_detail", args=[resident.id]))
        document.refresh_from_db()
        self.assertTrue(document.locked)

        queue_after_review = self.client.get(reverse("landlord_resident_files"))
        self.assertNotContains(queue_after_review, "Old Unit Packet")

    def test_landlord_can_add_room_rent_without_roster_entry(self):
        landlord = User.objects.create_user(
            username="manual-room-rent-landlord",
            email="manual-room-rent-landlord@example.com",
            password="StrongPass123!",
            role="landlord",
            is_staff=True,
        )
        property_obj = Property.objects.create(name="Manual Room Rent Property", landlord_email=landlord.email)

        self.client.login(username="manual-room-rent-landlord", password="StrongPass123!")
        response = self.client.post(reverse("landlord_rent_setup"), {
            "room_count": "0",
            "add_room_property_id": str(property_obj.id),
            "add_room_unit_label": "B",
            "add_room_monthly_rent": "525.00",
            "add_room_rent_due_day": "1",
            "add_room_utility_monthly": "0.00",
        })

        self.assertRedirects(response, reverse("landlord_rent_setup"))
        self.assertTrue(
            PropertyRoomRent.objects.filter(
                property=property_obj,
                room_unit_label="B",
                monthly_rent=Decimal("525.00"),
            ).exists()
        )

    def test_add_room_rent_wins_over_existing_blank_room_row(self):
        landlord = User.objects.create_user(
            username="add-room-existing-row-landlord",
            email="add-room-existing-row-landlord@example.com",
            password="StrongPass123!",
            role="landlord",
            is_staff=True,
        )
        property_obj = Property.objects.create(name="Add Room Existing Row Property", landlord_email=landlord.email)
        resident = HousingApplication.objects.create(
            property=property_obj,
            full_name="Existing Row Resident",
            phone="555-0189",
            email="existing-row@example.com",
            age=45,
            income_source="Employment",
            monthly_income=Decimal("3000.00"),
            housing_need="Current resident.",
            space_type="Room",
            space_label="B",
            monthly_rent=Decimal("0.00"),
            balance=Decimal("0.00"),
            utility_monthly=Decimal("0.00"),
            utility_balance=Decimal("0.00"),
        )

        self.client.login(username="add-room-existing-row-landlord", password="StrongPass123!")
        response = self.client.post(reverse("landlord_rent_setup"), {
            "room_count": "1",
            "room_0_property_id": str(property_obj.id),
            "room_0_room_unit_label": "B",
            "room_0_monthly_rent": "0.00",
            "room_0_rent_due_day": "1",
            "room_0_utility_monthly": "0.00",
            "room_0_deposit_required": "0.00",
            "room_0_deposit_paid": "0.00",
            "add_room_property_id": str(property_obj.id),
            "add_room_unit_label": "B",
            "add_room_monthly_rent": "506.00",
            "add_room_rent_due_day": "1",
            "add_room_utility_monthly": "55.00",
            "add_room_deposit_required": "450.00",
            "add_room_deposit_paid": "450.00",
            "apply_room_rents": "on",
        })

        self.assertRedirects(response, reverse("landlord_rent_setup"))
        room_rent = PropertyRoomRent.objects.get(property=property_obj, room_unit_label="B")
        self.assertEqual(room_rent.monthly_rent, Decimal("506.00"))
        self.assertEqual(room_rent.utility_monthly, Decimal("55.00"))
        self.assertEqual(room_rent.deposit_required, Decimal("450.00"))
        resident.refresh_from_db()
        self.assertEqual(resident.monthly_rent, Decimal("506.00"))
        self.assertEqual(resident.balance, Decimal("506.00"))
        self.assertEqual(resident.utility_monthly, Decimal("55.00"))
        self.assertEqual(resident.utility_balance, Decimal("55.00"))
        self.assertEqual(resident.deposit_required, Decimal("450.00"))
        self.assertEqual(resident.deposit_paid, Decimal("450.00"))

    def test_top_add_room_save_updates_existing_room_and_skips_table_rows(self):
        landlord = User.objects.create_user(
            username="top-add-room-landlord",
            email="top-add-room-landlord@example.com",
            password="StrongPass123!",
            role="landlord",
            is_staff=True,
        )
        property_obj = Property.objects.create(name="Top Add Room Property", landlord_email=landlord.email)
        resident = HousingApplication.objects.create(
            property=property_obj,
            full_name="Top Add Room G Resident",
            phone="555-0198",
            email="top-add-room-g@example.com",
            age=45,
            income_source="Employment",
            monthly_income=Decimal("3000.00"),
            housing_need="Current resident.",
            space_type="Room",
            space_label="G",
            monthly_rent=Decimal("0.00"),
            balance=Decimal("0.00"),
            utility_monthly=Decimal("0.00"),
            utility_balance=Decimal("0.00"),
        )

        self.client.login(username="top-add-room-landlord", password="StrongPass123!")
        response = self.client.post(reverse("landlord_rent_setup"), {
            "room_count": "1",
            "room_0_property_id": str(property_obj.id),
            "room_0_room_unit_label": "G",
            "room_0_monthly_rent": "0.00",
            "room_0_rent_due_day": "1",
            "room_0_utility_monthly": "0.00",
            "room_0_deposit_required": "0.00",
            "room_0_deposit_paid": "0.00",
            "add_room_property_id": str(property_obj.id),
            "add_room_unit_label": "G",
            "add_room_monthly_rent": "560.00",
            "add_room_rent_due_day": "1",
            "add_room_utility_monthly": "55.00",
            "add_room_deposit_required": "450.00",
            "add_room_deposit_paid": "450.00",
            "apply_room_rents": "on",
            "save_added_room": "1",
        })

        self.assertRedirects(response, reverse("landlord_rent_setup"))
        room_rent = PropertyRoomRent.objects.get(property=property_obj, room_unit_label="G")
        self.assertEqual(room_rent.monthly_rent, Decimal("560.00"))
        self.assertEqual(room_rent.utility_monthly, Decimal("55.00"))
        resident.refresh_from_db()
        self.assertEqual(resident.monthly_rent, Decimal("560.00"))
        self.assertEqual(resident.balance, Decimal("560.00"))
        self.assertEqual(resident.utility_monthly, Decimal("55.00"))
        self.assertEqual(resident.utility_balance, Decimal("55.00"))

    def test_room_rent_save_updates_duplicate_room_records(self):
        landlord = User.objects.create_user(
            username="duplicate-room-rent-landlord",
            email="duplicate-room-rent-landlord@example.com",
            password="StrongPass123!",
            role="landlord",
            is_staff=True,
        )
        property_obj = Property.objects.create(name="Duplicate Room Rent Property", landlord_email=landlord.email)
        resident = HousingApplication.objects.create(
            property=property_obj,
            full_name="Duplicate Room G Resident",
            phone="555-0199",
            email="duplicate-room-g@example.com",
            age=45,
            income_source="Employment",
            monthly_income=Decimal("3000.00"),
            housing_need="Current resident.",
            space_type="Room",
            space_label="Room G",
            monthly_rent=Decimal("0.00"),
            balance=Decimal("0.00"),
            utility_monthly=Decimal("0.00"),
            utility_balance=Decimal("0.00"),
        )
        PropertyRoomRent.objects.create(
            property=property_obj,
            room_unit_label="G",
            monthly_rent=Decimal("0.00"),
            utility_monthly=Decimal("0.00"),
            deposit_required=Decimal("0.00"),
        )
        PropertyRoomRent.objects.create(
            property=property_obj,
            room_unit_label="Room G",
            monthly_rent=Decimal("0.00"),
            utility_monthly=Decimal("0.00"),
            deposit_required=Decimal("0.00"),
        )

        self.client.login(username="duplicate-room-rent-landlord", password="StrongPass123!")
        response = self.client.post(reverse("landlord_rent_setup"), {
            "room_count": "1",
            "room_0_property_id": str(property_obj.id),
            "room_0_room_unit_label": "G",
            "room_0_monthly_rent": "0.00",
            "room_0_rent_due_day": "1",
            "room_0_utility_monthly": "0.00",
            "room_0_deposit_required": "0.00",
            "room_0_deposit_paid": "0.00",
            "add_room_property_id": str(property_obj.id),
            "add_room_unit_label": "G",
            "add_room_monthly_rent": "560.00",
            "add_room_rent_due_day": "1",
            "add_room_utility_monthly": "55.00",
            "add_room_deposit_required": "450.00",
            "add_room_deposit_paid": "450.00",
            "apply_room_rents": "on",
            "save_added_room": "1",
        })

        self.assertRedirects(response, reverse("landlord_rent_setup"))
        self.assertEqual(
            set(PropertyRoomRent.objects.filter(property=property_obj).values_list("monthly_rent", flat=True)),
            {Decimal("560.00")},
        )
        self.assertEqual(
            set(PropertyRoomRent.objects.filter(property=property_obj, is_active=True).values_list("room_unit_label", flat=True)),
            {"G"},
        )
        resident.refresh_from_db()
        self.assertEqual(resident.monthly_rent, Decimal("560.00"))
        self.assertEqual(resident.balance, Decimal("560.00"))

    def test_room_rent_save_preserves_payments_already_applied_to_balance(self):
        landlord = User.objects.create_user(
            username="paid-room-rent-landlord",
            email="paid-room-rent-landlord@example.com",
            password="StrongPass123!",
            role="landlord",
            is_staff=True,
        )
        property_obj = Property.objects.create(name="Paid Room Rent Property", landlord_email=landlord.email)
        resident = HousingApplication.objects.create(
            property=property_obj,
            full_name="Paid Room G Resident",
            phone="555-0200",
            email="paid-room-g@example.com",
            age=45,
            income_source="Employment",
            monthly_income=Decimal("3000.00"),
            housing_need="Current resident.",
            space_type="Room",
            space_label="G",
            monthly_rent=Decimal("650.00"),
            balance=Decimal("0.00"),
            utility_monthly=Decimal("55.00"),
            utility_balance=Decimal("0.00"),
        )
        PropertyRoomRent.objects.create(
            property=property_obj,
            room_unit_label="G",
            monthly_rent=Decimal("650.00"),
            utility_monthly=Decimal("55.00"),
            deposit_required=Decimal("450.00"),
        )
        Payment.objects.create(
            application=resident,
            payment_type="rent",
            payment_method="cash",
            amount=Decimal("650.00"),
            status="completed",
        )

        self.client.login(username="paid-room-rent-landlord", password="StrongPass123!")
        response = self.client.post(reverse("landlord_rent_setup"), {
            "room_count": "1",
            "room_0_property_id": str(property_obj.id),
            "room_0_room_unit_label": "G",
            "room_0_monthly_rent": "650.00",
            "room_0_rent_due_day": "1",
            "room_0_utility_monthly": "55.00",
            "room_0_deposit_required": "450.00",
            "room_0_deposit_paid": "450.00",
            "apply_room_rents": "on",
        })

        self.assertRedirects(response, reverse("landlord_rent_setup"))
        resident.refresh_from_db()
        self.assertEqual(resident.monthly_rent, Decimal("650.00"))
        self.assertEqual(resident.balance, Decimal("0.00"))
        self.assertEqual(resident.utility_balance, Decimal("0.00"))

    def test_room_letter_rent_applies_to_existing_resident_file(self):
        landlord = User.objects.create_user(
            username="apply-room-rent-landlord",
            email="apply-room-rent-landlord@example.com",
            password="StrongPass123!",
            role="landlord",
            is_staff=True,
        )
        property_obj = Property.objects.create(name="Apply Room Rent Property", landlord_email=landlord.email)
        resident = HousingApplication.objects.create(
            property=property_obj,
            full_name="Room Letter Resident",
            phone="555-0116",
            email="room-letter@example.com",
            age=45,
            income_source="Employment",
            monthly_income=Decimal("3000.00"),
            housing_need="Current resident.",
            space_type="Room",
            space_label="Q",
            monthly_rent=Decimal("0.00"),
            balance=Decimal("0.00"),
            utility_monthly=Decimal("0.00"),
            utility_balance=Decimal("0.00"),
        )

        self.client.login(username="apply-room-rent-landlord", password="StrongPass123!")
        self.client.post(reverse("landlord_rent_setup"), {
            "room_count": "1",
            "room_0_property_id": str(property_obj.id),
            "room_0_room_unit_label": "Q",
            "room_0_monthly_rent": "600.00",
            "room_0_rent_due_day": "1",
            "room_0_utility_monthly": "75.00",
            "room_0_deposit_required": "450.00",
            "room_0_deposit_paid": "95.00",
            "apply_room_rents": "on",
            f"resident_{resident.id}_monthly_rent": "0.00",
            f"resident_{resident.id}_balance": "0.00",
            f"resident_{resident.id}_rent_due_day": "1",
            f"resident_{resident.id}_utility_monthly": "0.00",
            f"resident_{resident.id}_utility_balance": "0.00",
            f"resident_{resident.id}_deposit_required": "0.00",
            f"resident_{resident.id}_deposit_paid": "0.00",
        })

        resident.refresh_from_db()
        self.assertEqual(resident.monthly_rent, Decimal("600.00"))
        self.assertEqual(resident.balance, Decimal("600.00"))
        self.assertEqual(resident.utility_monthly, Decimal("75.00"))
        self.assertEqual(resident.utility_balance, Decimal("75.00"))
        self.assertEqual(resident.deposit_required, Decimal("450.00"))
        self.assertEqual(resident.deposit_paid, Decimal("95.00"))
        self.assertTrue(RentHistory.objects.filter(application=resident, rent_amount=Decimal("600.00")).exists())

    def test_room_rent_setup_matches_room_prefix_aliases(self):
        landlord = User.objects.create_user(
            username="room-alias-rent-landlord",
            email="room-alias-rent-landlord@example.com",
            password="StrongPass123!",
            role="landlord",
            is_staff=True,
        )
        property_obj = Property.objects.create(name="Room Alias Rent Property", landlord_email=landlord.email)
        resident = HousingApplication.objects.create(
            property=property_obj,
            full_name="Room Alias Resident",
            phone="555-0188",
            email="room-alias@example.com",
            age=45,
            income_source="Employment",
            monthly_income=Decimal("3000.00"),
            housing_need="Current resident.",
            space_type="Room",
            space_label="Room B",
            monthly_rent=Decimal("0.00"),
            balance=Decimal("0.00"),
            utility_monthly=Decimal("0.00"),
            utility_balance=Decimal("0.00"),
        )
        CurrentResidentRosterEntry.objects.create(
            property=property_obj,
            first_name="Room",
            last_name="Alias Resident",
            email="room-alias@example.com",
            room_unit_label="B",
            uploaded_by=landlord,
        )

        self.client.login(username="room-alias-rent-landlord", password="StrongPass123!")
        response = self.client.get(reverse("landlord_rent_setup"))

        rows = [
            row for row in response.context["room_rows"]
            if row["property"] == property_obj and row["room_unit_label"] == "B"
        ]
        self.assertEqual(len(rows), 1)
        self.assertIn("Room Alias Resident", rows[0]["residents"])

        self.client.post(reverse("landlord_rent_setup"), {
            "room_count": "1",
            "room_0_property_id": str(property_obj.id),
            "room_0_room_unit_label": "B",
            "room_0_monthly_rent": "506.00",
            "room_0_rent_due_day": "1",
            "room_0_utility_monthly": "55.00",
            "room_0_deposit_required": "450.00",
            "room_0_deposit_paid": "450.00",
            "apply_room_rents": "on",
        })

        resident.refresh_from_db()
        self.assertEqual(resident.monthly_rent, Decimal("506.00"))
        self.assertEqual(resident.balance, Decimal("506.00"))
        self.assertEqual(resident.utility_monthly, Decimal("55.00"))
        self.assertEqual(resident.utility_balance, Decimal("55.00"))
        self.assertEqual(resident.deposit_required, Decimal("450.00"))
        self.assertEqual(resident.deposit_paid, Decimal("450.00"))

    def test_rent_setup_hides_orphan_existing_resident_setup_files(self):
        landlord = User.objects.create_user(
            username="orphan-setup-landlord",
            email="orphan-setup-landlord@example.com",
            password="StrongPass123!",
            role="landlord",
            is_staff=True,
        )
        property_obj = Property.objects.create(name="Orphan Setup Property", landlord_email=landlord.email)
        HousingApplication.objects.create(
            property=property_obj,
            full_name="Deleted Setup Person",
            phone="555-0191",
            email="deleted-setup@example.com",
            age=0,
            income_source="Existing resident intake",
            monthly_income=Decimal("0.00"),
            housing_need="Existing resident profile setup.",
            space_type="Room",
            space_label="Z",
            monthly_rent=Decimal("900.00"),
            balance=Decimal("900.00"),
        )
        regular_application = HousingApplication.objects.create(
            property=property_obj,
            full_name="Real Application Person",
            phone="555-0192",
            email="real-application@example.com",
            age=44,
            income_source="Employment",
            monthly_income=Decimal("3000.00"),
            housing_need="Application approved.",
            space_type="Room",
            space_label="Y",
            monthly_rent=Decimal("700.00"),
            balance=Decimal("700.00"),
        )

        self.client.login(username="orphan-setup-landlord", password="StrongPass123!")
        response = self.client.get(reverse("landlord_rent_setup"))

        resident_names = [
            resident_name
            for row in response.context["room_rows"]
            for resident_name in row["residents"]
        ]
        self.assertNotIn("Deleted Setup Person", resident_names)
        self.assertIn(regular_application.full_name, resident_names)

    def test_rent_setup_keeps_completed_existing_resident_file_without_intake(self):
        landlord = User.objects.create_user(
            username="completed-setup-landlord",
            email="completed-setup-landlord@example.com",
            password="StrongPass123!",
            role="landlord",
            is_staff=True,
        )
        resident_user = User.objects.create_user(
            username="completed-room-g",
            email="completed-room-g@example.com",
            password="StrongPass123!",
            role="tenant",
        )
        property_obj = Property.objects.create(name="Completed Setup Property", landlord_email=landlord.email)
        resident = HousingApplication.objects.create(
            property=property_obj,
            user=resident_user,
            full_name="David G. Kellum",
            phone="555-0193",
            email="completed-room-g@example.com",
            age=0,
            income_source="Existing resident intake",
            monthly_income=Decimal("0.00"),
            housing_need="Existing resident profile setup.",
            space_type="Room",
            space_label="Room G",
            monthly_rent=Decimal("0.00"),
            balance=Decimal("0.00"),
            utility_monthly=Decimal("0.00"),
            utility_balance=Decimal("0.00"),
        )

        self.client.login(username="completed-setup-landlord", password="StrongPass123!")
        response = self.client.get(reverse("landlord_rent_setup"))

        rows = [
            row for row in response.context["room_rows"]
            if row["property"] == property_obj and row["room_unit_label"] == "G"
        ]
        self.assertEqual(len(rows), 1)
        self.assertIn("David G. Kellum", rows[0]["residents"])

        save_response = self.client.post(reverse("landlord_rent_setup"), {
            "room_count": "1",
            "room_0_property_id": str(property_obj.id),
            "room_0_room_unit_label": "G",
            "room_0_monthly_rent": "560.00",
            "room_0_rent_due_day": "1",
            "room_0_utility_monthly": "55.00",
            "room_0_deposit_required": "450.00",
            "room_0_deposit_paid": "450.00",
            "apply_room_rents": "on",
        })

        self.assertRedirects(save_response, reverse("landlord_rent_setup"))
        resident.refresh_from_db()
        self.assertEqual(resident.monthly_rent, Decimal("560.00"))
        self.assertEqual(resident.balance, Decimal("560.00"))
        self.assertEqual(resident.utility_monthly, Decimal("55.00"))
        self.assertEqual(resident.utility_balance, Decimal("55.00"))

    def test_rent_setup_keeps_pending_setup_file_and_cleans_room_prefix(self):
        landlord = User.objects.create_user(
            username="pending-setup-landlord",
            email="pending-setup-landlord@example.com",
            password="StrongPass123!",
            role="landlord",
            is_staff=True,
        )
        pending_user = User.objects.create_user(
            username="pending-room-g",
            email="pending-room-g@example.com",
            password=None,
            role="tenant",
        )
        property_obj = Property.objects.create(name="Pending Setup Property", landlord_email=landlord.email)
        resident = HousingApplication.objects.create(
            property=property_obj,
            user=pending_user,
            full_name="Room G Resident",
            phone="555-0194",
            email="pending-room-g@example.com",
            age=0,
            income_source="Existing resident intake",
            monthly_income=Decimal("0.00"),
            housing_need="Existing resident profile setup.",
            space_type="Room",
            space_label="Room G",
            monthly_rent=Decimal("0.00"),
            balance=Decimal("0.00"),
            utility_monthly=Decimal("0.00"),
            utility_balance=Decimal("0.00"),
        )

        self.client.login(username="pending-setup-landlord", password="StrongPass123!")
        response = self.client.get(reverse("landlord_rent_setup"))

        rows = [
            row for row in response.context["room_rows"]
            if row["property"] == property_obj and row["room_unit_label"] == "G"
        ]
        self.assertEqual(len(rows), 1)
        self.assertIn("Room G Resident", rows[0]["residents"])

        save_response = self.client.post(reverse("landlord_rent_setup"), {
            "room_count": "1",
            "room_0_property_id": str(property_obj.id),
            "room_0_room_unit_label": "G",
            "room_0_monthly_rent": "560.00",
            "room_0_rent_due_day": "1",
            "room_0_utility_monthly": "55.00",
            "room_0_deposit_required": "450.00",
            "room_0_deposit_paid": "450.00",
            "apply_room_rents": "on",
        })

        self.assertRedirects(save_response, reverse("landlord_rent_setup"))
        resident.refresh_from_db()
        room_setting = PropertyRoomRent.objects.get(property=property_obj)
        self.assertEqual(room_setting.room_unit_label, "G")
        self.assertEqual(resident.monthly_rent, Decimal("560.00"))
        self.assertEqual(resident.balance, Decimal("560.00"))
        self.assertEqual(resident.utility_monthly, Decimal("55.00"))
        self.assertEqual(resident.utility_balance, Decimal("55.00"))

    def test_single_room_save_updates_only_selected_room(self):
        landlord = User.objects.create_user(
            username="single-room-save-landlord",
            email="single-room-save-landlord@example.com",
            password="StrongPass123!",
            role="landlord",
            is_staff=True,
        )
        property_obj = Property.objects.create(name="Single Room Save Property", landlord_email=landlord.email)
        room_g_resident = HousingApplication.objects.create(
            property=property_obj,
            full_name="Room G Resident",
            phone="555-0195",
            email="room-g-single-save@example.com",
            age=45,
            income_source="Employment",
            monthly_income=Decimal("3000.00"),
            housing_need="Current resident.",
            space_type="Room",
            space_label="G",
            monthly_rent=Decimal("0.00"),
            balance=Decimal("0.00"),
        )
        room_l_resident = HousingApplication.objects.create(
            property=property_obj,
            full_name="Room L Resident",
            phone="555-0196",
            email="room-l-single-save@example.com",
            age=45,
            income_source="Employment",
            monthly_income=Decimal("3000.00"),
            housing_need="Current resident.",
            space_type="Room",
            space_label="L",
            monthly_rent=Decimal("0.00"),
            balance=Decimal("0.00"),
        )

        self.client.login(username="single-room-save-landlord", password="StrongPass123!")
        response = self.client.post(reverse("landlord_rent_setup"), {
            "room_count": "2",
            "room_update_index": "0",
            "room_0_property_id": str(property_obj.id),
            "room_0_room_unit_label": "G",
            "room_0_monthly_rent": "560.00",
            "room_0_rent_due_day": "1",
            "room_0_utility_monthly": "55.00",
            "room_0_deposit_required": "450.00",
            "room_0_deposit_paid": "450.00",
            "room_1_property_id": str(property_obj.id),
            "room_1_room_unit_label": "L",
            "room_1_monthly_rent": "0.00",
            "room_1_rent_due_day": "1",
            "room_1_utility_monthly": "0.00",
            "room_1_deposit_required": "0.00",
            "room_1_deposit_paid": "0.00",
            "apply_room_rents": "on",
        })

        self.assertRedirects(response, reverse("landlord_rent_setup"))
        room_g_resident.refresh_from_db()
        room_l_resident.refresh_from_db()
        self.assertEqual(room_g_resident.monthly_rent, Decimal("560.00"))
        self.assertEqual(room_g_resident.balance, Decimal("560.00"))
        self.assertEqual(room_l_resident.monthly_rent, Decimal("0.00"))
        self.assertFalse(PropertyRoomRent.objects.filter(property=property_obj, room_unit_label="L").exists())

    def test_landlord_rent_setup_does_not_update_other_property_resident(self):
        landlord = User.objects.create_user(
            username="blocked-rent-setup-landlord",
            email="blocked-rent-setup-landlord@example.com",
            password="StrongPass123!",
            role="landlord",
            is_staff=True,
        )
        property_obj = Property.objects.create(name="Allowed Rent Setup Property", landlord_email=landlord.email)
        other_property = Property.objects.create(name="Other Rent Setup Property", landlord_email="other@example.com")
        allowed_resident = HousingApplication.objects.create(
            property=property_obj,
            full_name="Allowed Rent Resident",
            phone="555-0113",
            email="allowed-rent@example.com",
            age=46,
            income_source="Employment",
            monthly_income=Decimal("3000.00"),
            housing_need="Current resident.",
        )
        other_resident = HousingApplication.objects.create(
            property=other_property,
            full_name="Other Rent Resident",
            phone="555-0114",
            email="other-rent@example.com",
            age=46,
            income_source="Employment",
            monthly_income=Decimal("3000.00"),
            housing_need="Current resident.",
            monthly_rent=Decimal("400.00"),
            balance=Decimal("400.00"),
        )

        self.client.login(username="blocked-rent-setup-landlord", password="StrongPass123!")
        self.client.post(reverse("landlord_rent_setup"), {
            f"resident_{allowed_resident.id}_monthly_rent": "500.00",
            f"resident_{allowed_resident.id}_balance": "500.00",
            f"resident_{allowed_resident.id}_rent_due_day": "1",
            f"resident_{allowed_resident.id}_utility_monthly": "0.00",
            f"resident_{allowed_resident.id}_utility_balance": "0.00",
            f"resident_{other_resident.id}_monthly_rent": "999.00",
            f"resident_{other_resident.id}_balance": "999.00",
            f"resident_{other_resident.id}_rent_due_day": "1",
            f"resident_{other_resident.id}_utility_monthly": "0.00",
            f"resident_{other_resident.id}_utility_balance": "0.00",
        })

        other_resident.refresh_from_db()
        self.assertEqual(other_resident.monthly_rent, Decimal("400.00"))
        self.assertEqual(other_resident.balance, Decimal("400.00"))

    def test_group_message_sms_logs_only_when_selected_and_requires_consent(self):
        landlord = User.objects.create_user(
            username="group-sms-landlord",
            email="group-sms-landlord@example.com",
            password="StrongPass123!",
            role="landlord",
            is_staff=True,
        )
        resident_user = User.objects.create_user(username="group-sms-resident", password="StrongPass123!", role="tenant")
        property_obj = Property.objects.create(name="Group SMS Property", landlord_email=landlord.email)
        application = HousingApplication.objects.create(
            property=property_obj,
            user=resident_user,
            full_name="Group SMS Resident",
            phone="555-0110",
            email="group-sms-resident@example.com",
            age=46,
            income_source="Employment",
            monthly_income=Decimal("3000.00"),
            housing_need="Current resident.",
            sms_opted_in=False,
        )

        self.client.login(username="group-sms-landlord", password="StrongPass123!")
        response = self.client.post(reverse("group_resident_message"), {
            "property_id": str(property_obj.id),
            "delivery_method": "portal_sms",
            "subject": "SMS Notice",
            "message": "This notice should be logged, not sent.",
        })

        self.assertRedirects(response, reverse("group_resident_message"))
        log = SmsMessageLog.objects.get(application=application)
        self.assertEqual(log.status, "skipped_no_consent")

    @override_settings(SMS_PROVIDER="telnyx", TELNYX_API_KEY="key-local", TELNYX_FROM_NUMBER="+15415550100")
    @patch("main.views.urlopen")
    def test_telnyx_sms_provider_sends_opted_in_group_message(self, mocked_urlopen):
        class FakeResponse:
            def read(self):
                return b'{"data":{"id":"telnyx-message-123"}}'

        mocked_urlopen.return_value = FakeResponse()
        landlord = User.objects.create_user(
            username="telnyx-sms-landlord",
            email="telnyx-sms-landlord@example.com",
            password="StrongPass123!",
            role="landlord",
            is_staff=True,
        )
        resident_user = User.objects.create_user(username="telnyx-sms-resident", password="StrongPass123!", role="tenant")
        property_obj = Property.objects.create(name="Telnyx SMS Property", landlord_email=landlord.email)
        application = HousingApplication.objects.create(
            property=property_obj,
            user=resident_user,
            full_name="Telnyx SMS Resident",
            phone="541-555-0110",
            email="telnyx-sms-resident@example.com",
            age=46,
            income_source="Employment",
            monthly_income=Decimal("3000.00"),
            housing_need="Current resident.",
            sms_opted_in=True,
        )

        self.client.login(username="telnyx-sms-landlord", password="StrongPass123!")
        response = self.client.post(reverse("group_resident_message"), {
            "property_id": str(property_obj.id),
            "delivery_method": "portal_sms",
            "subject": "SMS Notice",
            "message": "This notice should be sent through Telnyx.",
        })

        self.assertRedirects(response, reverse("group_resident_message"))
        log = SmsMessageLog.objects.get(application=application)
        self.assertEqual(log.status, "sent")
        self.assertEqual(log.provider_message_id, "telnyx-message-123")
        request = mocked_urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.telnyx.com/v2/messages")
        self.assertIn(b'"to": "+15415550110"', request.data)

    def test_twilio_stop_webhook_opts_out_matching_resident_phone(self):
        resident_user = User.objects.create_user(username="sms-stop-resident", password="StrongPass123!", role="tenant")
        application = HousingApplication.objects.create(
            user=resident_user,
            full_name="SMS Stop Resident",
            phone="+15550111",
            email="sms-stop-resident@example.com",
            age=46,
            income_source="Employment",
            monthly_income=Decimal("3000.00"),
            housing_need="Current resident.",
            sms_opted_in=True,
        )

        response = self.client.post(reverse("twilio_sms_webhook"), {
            "From": "+1 (555) 0111",
            "Body": "STOP",
        })

        self.assertEqual(response.status_code, 200)
        application.refresh_from_db()
        self.assertFalse(application.sms_opted_in)
        self.assertIsNotNone(application.sms_opted_out_at)

    def test_create_tenant_without_application_redirects_to_dashboard(self):
        staff_user = User.objects.create_user(
            username="staff",
            email="staff@example.com",
            password="StrongPass123!",
            role="landlord",
            is_staff=True,
        )

        self.client.login(username="staff", password="StrongPass123!")

        response = self.client.get(reverse("landlord_create_tenant"))

        self.assertRedirects(response, reverse("landlord_dashboard"))

    def test_resident_can_sign_emergency_contact_and_locked_copy_remains_viewable(self):
        user = User.objects.create_user(
            username="resident-doc",
            email="resident-doc@example.com",
            password="StrongPass123!",
            role="tenant",
        )
        application = HousingApplication.objects.create(
            user=user,
            full_name="Document Resident",
            phone="555-0110",
            email="resident-doc@example.com",
            age=51,
            income_source="Employment",
            monthly_income=Decimal("3000.00"),
            housing_need="Current resident.",
        )
        signed_document = SignedDocument.objects.create(
            application=application,
            document_type="emergency_contact",
            title="Emergency Contact Sheet",
        )

        self.client.login(username="resident-doc", password="StrongPass123!")

        response = self.client.post(reverse("submit_onboarding_document", args=[signed_document.id]), {
            "emergency_contact_name": "Emergency Person",
            "emergency_contact_phone": "555-0198",
            "emergency_contact_relationship": "Friend",
            "resident_signature": "Document Resident",
            "signature_agreement": "on",
        })

        self.assertRedirects(response, reverse("tenant_dashboard"))
        signed_document.refresh_from_db()
        self.assertTrue(signed_document.locked)
        self.assertEqual(signed_document.emergency_contact_name, "Emergency Person")

        response = self.client.get(reverse("onboarding_document", args=[signed_document.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "viewable but no longer editable")
        self.assertContains(response, "Emergency Person")

    def test_resident_signs_selected_lease_document(self):
        user = User.objects.create_user(
            username="resident-selected-lease",
            email="resident-selected-lease@example.com",
            password="StrongPass123!",
            role="tenant",
        )
        application = HousingApplication.objects.create(
            user=user,
            full_name="Selected Lease Resident",
            phone="555-0119",
            email="resident-selected-lease@example.com",
            age=51,
            income_source="Employment",
            monthly_income=Decimal("3000.00"),
            housing_need="Current resident.",
        )
        original_lease = SignedDocument.objects.create(
            application=application,
            document_type="lease",
            title="Original Lease",
        )
        platform_lease = SignedDocument.objects.create(
            application=application,
            document_type="lease",
            title="Platform Lease Update",
        )

        self.client.login(username="resident-selected-lease", password="StrongPass123!")

        response = self.client.post(reverse("submit_onboarding_document", args=[platform_lease.id]), {
            "rent_initials": "SL",
            "sobriety_initials": "SL",
            "testing_initials": "SL",
            "guest_policy_initials": "SL",
            "cleanliness_initials": "SL",
            "disclosure_initials": "SL",
            "resident_signature": "Selected Lease Resident",
            "signature_agreement": "on",
        })

        self.assertRedirects(response, reverse("tenant_dashboard"))
        original_lease.refresh_from_db()
        platform_lease.refresh_from_db()
        self.assertFalse(original_lease.locked)
        self.assertTrue(platform_lease.locked)

    def test_resident_can_upload_profile_photo(self):
        user = User.objects.create_user(
            username="photo-resident",
            email="photo-resident@example.com",
            password="StrongPass123!",
            role="tenant",
        )
        application = HousingApplication.objects.create(
            user=user,
            full_name="Photo Resident",
            phone="555-0111",
            email="photo-resident@example.com",
            age=52,
            income_source="Employment",
            monthly_income=Decimal("3000.00"),
            housing_need="Current resident.",
        )
        image = SimpleUploadedFile(
            "resident.gif",
            b"GIF87a\x01\x00\x01\x00\x80\x01\x00\x00\x00\x00ccc,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;",
            content_type="image/gif",
        )

        self.client.login(username="photo-resident", password="StrongPass123!")

        dashboard_response = self.client.get(reverse("tenant_dashboard"))

        self.assertContains(dashboard_response, "Change Photo")

        response = self.client.post(reverse("update_resident_profile_photo"), {
            "profile_photo": image,
        })

        self.assertRedirects(response, reverse("tenant_dashboard"))
        application.refresh_from_db()
        self.assertTrue(application.profile_photo.name)

    def test_superadmin_can_inspect_tenant_dashboard_by_resident_file(self):
        superuser = User.objects.create_user(
            username="superadmin",
            email="super@example.com",
            password="StrongPass123!",
            role="admin",
            is_staff=True,
        )
        application = HousingApplication.objects.create(
            full_name="Inspect Resident",
            phone="5550112233",
            email="inspect@example.com",
            age=53,
            income_source="Employment",
            monthly_income=Decimal("3000.00"),
            housing_need="Current resident.",
        )

        self.client.login(username="superadmin", password="StrongPass123!")

        response = self.client.get(f"{reverse('tenant_dashboard')}?resident={application.id}")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Inspect Resident")
        self.assertContains(response, "(555) 011-2233")
        self.assertContains(response, "Renters Insurance")
        self.assertContains(response, "Back to Super Admin Dashboard")

    def test_superadmin_owners_page_lists_properties_without_owner_email(self):
        User.objects.create_user(
            username="superadmin",
            email="super@example.com",
            password="StrongPass123!",
            role="admin",
            is_staff=True,
        )
        Property.objects.create(name="Painted Lady Inn", owner_email="")

        self.client.login(username="superadmin", password="StrongPass123!")

        response = self.client.get(reverse("superadmin_owners"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Unassigned Owner")
        self.assertContains(response, "Painted Lady Inn")

    def test_superadmin_dashboard_links_company_mailbox(self):
        User.objects.create_user(
            username="superadmin-mailbox",
            email="superadmin-mailbox@example.com",
            password="StrongPass123!",
            role="admin",
            is_staff=True,
        )

        self.client.login(username="superadmin-mailbox", password="StrongPass123!")
        response = self.client.get(reverse("superadmin_dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Company Inbox")
        self.assertContains(response, reverse("company_mailbox"))

    def test_superadmin_company_mailbox_lists_graph_messages(self):
        superuser = User.objects.create_user(
            username="superadmin-mailbox-list",
            email="superadmin-mailbox-list@example.com",
            password="StrongPass123!",
            role="admin",
            is_staff=True,
        )
        CompanyMailboxConnection.objects.create(
            mailbox_email="michael@bowlinglegacy.com",
            refresh_token="refresh-token",
            access_token="access-token",
            token_expires_at=timezone.now() + timezone.timedelta(hours=1),
            connected_by=superuser,
        )

        self.client.login(username="superadmin-mailbox-list", password="StrongPass123!")
        with patch("main.views.graph_request") as graph_request:
            graph_request.return_value = {
                "value": [{
                    "id": "message-1",
                    "subject": "Owner question",
                    "from": {"emailAddress": {"name": "Owner", "address": "owner@example.com"}},
                    "receivedDateTime": "2026-05-24T10:00:00Z",
                    "isRead": False,
                    "bodyPreview": "Can you help?",
                }]
            }
            response = self.client.get(reverse("company_mailbox"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Owner question")
        self.assertContains(response, "owner@example.com")

    def test_superadmin_company_mailbox_compose_sends_through_graph(self):
        superuser = User.objects.create_user(
            username="superadmin-mailbox-compose",
            email="superadmin-mailbox-compose@example.com",
            password="StrongPass123!",
            role="admin",
            is_staff=True,
        )
        CompanyMailboxConnection.objects.create(
            mailbox_email="michael@bowlinglegacy.com",
            refresh_token="refresh-token",
            access_token="access-token",
            token_expires_at=timezone.now() + timezone.timedelta(hours=1),
            connected_by=superuser,
        )

        self.client.login(username="superadmin-mailbox-compose", password="StrongPass123!")
        with patch("main.views.graph_request") as graph_request:
            graph_request.return_value = {}
            response = self.client.post(reverse("company_mailbox_compose"), {
                "to_email": "resident@example.com",
                "subject": "Hello",
                "body": "Message from dashboard.",
            })

        self.assertRedirects(response, reverse("company_mailbox"))
        graph_request.assert_called_once()
        self.assertEqual(graph_request.call_args.args[1], "POST")
        self.assertEqual(graph_request.call_args.args[2], "/me/sendMail")

    def test_superadmin_company_mailbox_cleans_marketing_email_body(self):
        superuser = User.objects.create_user(
            username="superadmin-mailbox-clean",
            email="superadmin-mailbox-clean@example.com",
            password="StrongPass123!",
            role="admin",
            is_staff=True,
        )
        CompanyMailboxConnection.objects.create(
            mailbox_email="michael@bowlinglegacy.com",
            refresh_token="refresh-token",
            access_token="access-token",
            token_expires_at=timezone.now() + timezone.timedelta(hours=1),
            connected_by=superuser,
        )

        self.client.login(username="superadmin-mailbox-clean", password="StrongPass123!")
        with patch("main.views.graph_request") as graph_request:
            graph_request.side_effect = [
                {
                    "id": "message-1",
                    "subject": "Stripe update",
                    "from": {"emailAddress": {"name": "Stripe", "address": "stripe@example.com"}},
                    "receivedDateTime": "2026-05-24T10:00:00Z",
                    "isRead": False,
                    "bodyPreview": "Unlock more",
                    "body": {
                        "contentType": "html",
                        "content": "<!-- #outlook a { padding:0 } @media only screen { .mj-column { width:100% } } --><style>.hide{display:none}</style><div>Unlock more&nbsp;with Stripe</div>\u200d\u200f [[https://stripe.com?utm_source=test]]<p>[ Stripe icon - Radar fraud prevention ]</p><p>Explore products</p><p>Explore products</p>",
                    },
                },
                {},
            ]
            response = self.client.get(reverse("company_mailbox_message", args=["message-1"]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Unlock more with Stripe")
        self.assertContains(response, "Explore products")
        self.assertNotContains(response, "utm_source")
        self.assertNotContains(response, "[[https://stripe.com")
        self.assertNotContains(response, "#outlook")
        self.assertNotContains(response, "Stripe icon")

    def test_superadmin_company_mailbox_can_delete_message(self):
        superuser = User.objects.create_user(
            username="superadmin-mailbox-delete",
            email="superadmin-mailbox-delete@example.com",
            password="StrongPass123!",
            role="admin",
            is_staff=True,
        )
        CompanyMailboxConnection.objects.create(
            mailbox_email="michael@bowlinglegacy.com",
            refresh_token="refresh-token",
            access_token="access-token",
            token_expires_at=timezone.now() + timezone.timedelta(hours=1),
            connected_by=superuser,
        )

        self.client.login(username="superadmin-mailbox-delete", password="StrongPass123!")
        with patch("main.views.graph_request") as graph_request:
            graph_request.return_value = {}
            response = self.client.post(reverse("company_mailbox_message", args=["message-1"]), {
                "action": "delete",
            })

        self.assertRedirects(response, reverse("company_mailbox"))
        graph_request.assert_called_once()
        self.assertEqual(graph_request.call_args.args[1], "DELETE")
        self.assertEqual(graph_request.call_args.args[2], "/me/messages/message-1")

    def test_property_owner_role_can_open_empty_owner_dashboard(self):
        User.objects.create_user(
            username="portfolio-owner",
            email="owner@example.com",
            password="StrongPass123!",
            role="property_owner",
        )

        response = self.client.post(reverse("login"), {
            "username": "portfolio-owner",
            "password": "StrongPass123!",
        })

        self.assertRedirects(response, reverse("property_owner_dashboard"))

        dashboard_response = self.client.get(reverse("property_owner_dashboard"))
        self.assertEqual(dashboard_response.status_code, 200)
        self.assertContains(dashboard_response, "No properties are connected to this owner yet.")

    def test_property_owner_can_add_property_invite_landlord_and_upload_financial_file(self):
        owner = User.objects.create_user(
            username="workflow-owner",
            email="workflow-owner@example.com",
            password="StrongPass123!",
            role="property_owner",
        )
        self.client.login(username="workflow-owner", password="StrongPass123!")

        property_response = self.client.post(reverse("owner_property_create"), {
            "name": "Owner Added Property",
            "address": "100 Owner Way",
            "description": "Owner created property.",
            "rent_amount": "1450.00",
            "lease_type": "lease",
            "availability_status": "full",
            "availability_message": "Profile setup underway",
        })

        self.assertRedirects(
            property_response,
            reverse("owner_property_onboarding_documents", args=[Property.objects.get(name="Owner Added Property").id]),
        )
        property_obj = Property.objects.get(name="Owner Added Property")
        self.assertEqual(property_obj.owner_email, owner.email)
        self.assertEqual(property_obj.rent_amount, Decimal("1450.00"))
        self.assertEqual(property_obj.lease_type, "lease")

        onboarding_response = self.client.post(
            reverse("owner_property_onboarding_documents", args=[property_obj.id]),
            {
                "application_file": SimpleUploadedFile("rental-application.pdf", b"application", content_type="application/pdf"),
                "lease_file": SimpleUploadedFile("lease.pdf", b"lease", content_type="application/pdf"),
                "other_documents": SimpleUploadedFile("house-rules.pdf", b"rules", content_type="application/pdf"),
            },
        )

        self.assertRedirects(onboarding_response, reverse("property_owner_dashboard"))
        self.assertEqual(
            set(PropertyOnboardingDocument.objects.filter(property=property_obj).values_list("document_type", flat=True)),
            {"application", "lease", "other"},
        )

        landlord_response = self.client.post(reverse("owner_landlord_invite"), {
            "property": property_obj.id,
            "full_name": "Assigned Landlord",
            "email": "assigned-landlord@example.com",
            "phone": "555-0197",
            "address": "200 Manager Way",
        })

        self.assertRedirects(landlord_response, reverse("property_owner_dashboard"))
        property_obj.refresh_from_db()
        self.assertEqual(property_obj.landlord_email, "assigned-landlord@example.com")
        intake = LandlordIntake.objects.get(email="assigned-landlord@example.com")
        self.assertEqual(intake.status, "invited")
        self.assertTrue(intake.user.invite_code)
        self.assertEqual(len(mail.outbox), 1)

        financial_file = SimpleUploadedFile("owner.csv", b"date,amount\n2026-05-01,100", content_type="text/csv")
        upload_response = self.client.post(reverse("owner_financial_upload"), {
            "property": property_obj.id,
            "name": "Owner Upload",
            "file": financial_file,
            "notes": "QuickBooks export",
        })

        self.assertRedirects(upload_response, reverse("owner_financial_upload"))
        self.assertEqual(property_obj.financial_uploads.get(name="Owner Upload").notes, "QuickBooks export")

    def test_property_owner_onboarding_wizard_tracks_setup_steps(self):
        owner = User.objects.create_user(
            username="wizard-owner",
            email="wizard-owner@example.com",
            password="StrongPass123!",
            role="property_owner",
        )
        property_obj = Property.objects.create(
            name="Wizard Property",
            address="10 Wizard Way",
            owner_email=owner.email,
            landlord_email="manager@example.com",
            rent_amount=Decimal("1200.00"),
        )
        PropertyRoomRent.objects.create(property=property_obj, room_unit_label="A", monthly_rent=Decimal("1200.00"))
        PropertyOnboardingDocument.objects.create(
            property=property_obj,
            document_type="application",
            title="Application",
            file=SimpleUploadedFile("application.pdf", b"application", content_type="application/pdf"),
        )
        PropertyOnboardingDocument.objects.create(
            property=property_obj,
            document_type="lease",
            title="Lease",
            file=SimpleUploadedFile("lease.pdf", b"lease", content_type="application/pdf"),
        )

        self.client.login(username="wizard-owner", password="StrongPass123!")

        response = self.client.get(reverse("owner_onboarding_wizard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Owner Onboarding Wizard")
        self.assertContains(response, "Wizard Property")
        self.assertContains(response, "Property profile")
        self.assertContains(response, "Onboarding documents")
        self.assertContains(response, "Units and rent setup")
        self.assertContains(response, "Landlord or manager")
        self.assertContains(response, "4 of 7 complete")

    def test_property_owner_intake_questionnaire_saves_system_needs(self):
        form_response = self.client.get(reverse("property_owner_intake"))
        self.assertEqual(form_response.status_code, 200)
        self.assertContains(form_response, "Tell us what your dashboard needs to do.")
        self.assertContains(form_response, "Submit Questionnaire")

        response = self.client.post(reverse("property_owner_intake"), {
            "full_name": "Portfolio Owner",
            "company_name": "North Street Holdings",
            "email": "portfolio@example.com",
            "phone": "555-0191",
            "property_count": "4",
            "total_units": "120",
            "property_types": ["multifamily", "commercial"],
            "current_software": "QuickBooks and spreadsheets",
            "needs_rent_collection": "on",
            "needs_accounting": "on",
            "needs_data_migration": "on",
            "charges_application_fee": "on",
            "performs_background_checks": "on",
            "advertises_available_units": "on",
            "uses_automatic_late_fees": "on",
            "needs_custom_reports": "on",
            "desired_reports": ["valuation_estimate", "vendor_expense", "utility_cost_trend"],
            "offers_renters_insurance": "on",
            "dashboard_goals": "Show NOI and rent collection by property.",
        })

        self.assertRedirects(response, reverse("property_owner_intake_success"))
        intake = PropertyOwnerIntake.objects.get(email="portfolio@example.com")
        self.assertEqual(intake.property_count, 4)
        self.assertEqual(intake.total_units, 120)
        self.assertEqual(intake.property_types, "multifamily,commercial")
        self.assertTrue(intake.needs_accounting)
        self.assertTrue(intake.needs_data_migration)
        self.assertTrue(intake.charges_application_fee)
        self.assertTrue(intake.performs_background_checks)
        self.assertTrue(intake.advertises_available_units)
        self.assertTrue(intake.uses_automatic_late_fees)
        self.assertTrue(intake.needs_custom_reports)
        self.assertEqual(intake.desired_reports, "valuation_estimate, vendor_expense, utility_cost_trend")
        self.assertTrue(intake.offers_renters_insurance)
        self.assertEqual(intake.lead_stage, "new")

    def test_existing_resident_intake_button_opens_for_new_property_and_saves_profile(self):
        property_obj = Property.objects.create(name="Painted Lady Inn")
        CurrentResidentRosterEntry.objects.create(
            property=property_obj,
            first_name="Existing",
            last_name="Resident",
            email="existing@example.com",
            phone="555-0195",
            room_unit_label="Room B",
        )

        property_response = self.client.get(reverse("property_detail", args=[property_obj.id]))
        self.assertEqual(property_response.status_code, 200)
        self.assertContains(property_response, "Existing Resident Profile")

        response = self.client.post(reverse("existing_resident_intake", args=[property_obj.id]), {
            "first_name": "Existing",
            "middle_name": "R",
            "last_name": "Resident",
            "email": "existing@example.com",
            "phone": "555-0195",
            "room_unit_label": "Room B",
            "sms_opted_in": "on",
            "has_valid_odl": "on",
            "years_at_residence": "3",
            "move_in_month": "2023-07",
        })

        self.assertRedirects(response, reverse("existing_resident_intake_success", args=[property_obj.id]))
        intake = ExistingResidentIntake.objects.get(email="existing@example.com")
        self.assertEqual(intake.property, property_obj)
        self.assertEqual(intake.full_name(), "Existing R Resident")
        self.assertEqual(intake.room_unit_label, "Room B")
        self.assertEqual(intake.move_in_month, "2023-07")
        self.assertTrue(intake.has_valid_odl)
        application = HousingApplication.objects.get(email="existing@example.com")
        self.assertEqual(application.property, property_obj)
        self.assertEqual(application.space_type, "Room")
        self.assertEqual(application.space_label, "Room B")
        self.assertIsNotNone(application.user)
        self.assertEqual(application.deposit_required, Decimal("0.00"))
        self.assertEqual(application.utility_monthly, Decimal("0.00"))
        self.assertTrue(application.sms_opted_in)
        self.assertIsNotNone(application.sms_opted_in_at)
        self.assertIn(application.user.invite_code, mail.outbox[0].body)

    def test_existing_resident_intake_does_not_auto_invite_without_roster_match(self):
        property_obj = Property.objects.create(name="Roster Protected Property")
        CurrentResidentRosterEntry.objects.create(
            property=property_obj,
            first_name="Approved",
            last_name="Resident",
            email="approved@example.com",
            room_unit_label="Room A",
        )

        response = self.client.post(reverse("existing_resident_intake", args=[property_obj.id]), {
            "first_name": "Unknown",
            "last_name": "Resident",
            "email": "unknown@example.com",
            "phone": "555-0196",
            "room_unit_label": "Room Z",
            "years_at_residence": "1",
        })

        self.assertRedirects(response, reverse("existing_resident_intake_success", args=[property_obj.id]))
        self.assertTrue(ExistingResidentIntake.objects.filter(email="unknown@example.com").exists())
        self.assertFalse(HousingApplication.objects.filter(email="unknown@example.com").exists())
        self.assertEqual(len(mail.outbox), 0)

    def test_headerless_resident_roster_allows_exact_name_setup_invite(self):
        landlord = User.objects.create_user(
            username="headerless-roster-landlord",
            email="headerless-roster-landlord@example.com",
            password="StrongPass123!",
            role="landlord",
            is_staff=True,
        )
        property_obj = Property.objects.create(name="Headerless Roster Property", landlord_email=landlord.email)
        roster_file = SimpleUploadedFile(
            "resident-list.csv",
            b"Grady Brady\nHero Lowe\nAaron Brown\n",
            content_type="text/csv",
        )

        self.client.login(username="headerless-roster-landlord", password="StrongPass123!")
        upload_response = self.client.post(reverse("current_resident_roster_upload"), {
            "property": property_obj.id,
            "file": roster_file,
        })

        self.assertRedirects(upload_response, reverse("current_resident_roster_upload"))
        self.assertTrue(
            CurrentResidentRosterEntry.objects.filter(
                property=property_obj,
                first_name="Hero",
                last_name="Lowe",
            ).exists()
        )

        setup_response = self.client.post(reverse("existing_resident_intake", args=[property_obj.id]), {
            "first_name": "HERO",
            "last_name": "LOWE",
            "email": "hero@example.com",
            "phone": "555-0197",
            "room_unit_label": "Room N",
            "years_at_residence": "1",
        })

        self.assertRedirects(setup_response, reverse("existing_resident_intake_success", args=[property_obj.id]))
        application = HousingApplication.objects.get(email="hero@example.com")
        self.assertEqual(application.full_name, "HERO LOWE")
        self.assertIn(application.user.invite_code, mail.outbox[0].body)

    def test_landlord_workspace_only_lists_assigned_property_records(self):
        landlord = User.objects.create_user(
            username="assigned-landlord",
            email="assigned@example.com",
            password="StrongPass123!",
            role="landlord",
            is_staff=True,
        )
        assigned_property = Property.objects.create(name="Assigned Property", landlord_email=landlord.email)
        other_property = Property.objects.create(name="Other Property", landlord_email="other@example.com")
        assigned_resident_user = User.objects.create_user(
            username="assigned-resident-user",
            email="assigned-resident@example.com",
            password="StrongPass123!",
            role="tenant",
        )
        assigned_application = HousingApplication.objects.create(
            property=assigned_property,
            user=assigned_resident_user,
            full_name="Assigned Resident",
            phone="555-0198",
            email="assigned-resident@example.com",
            age=51,
            income_source="Employment",
            monthly_income=Decimal("2500.00"),
            housing_need="Current resident.",
        )
        other_application = HousingApplication.objects.create(
            property=other_property,
            full_name="Other Resident",
            phone="555-0199",
            email="other-resident@example.com",
            age=52,
            income_source="Employment",
            monthly_income=Decimal("2500.00"),
            housing_need="Current resident.",
        )
        Payment.objects.create(application=assigned_application, amount=Decimal("100.00"), status="completed")
        Payment.objects.create(application=other_application, amount=Decimal("200.00"), status="completed")

        self.client.login(username="assigned-landlord", password="StrongPass123!")

        resident_files = self.client.get(reverse("landlord_resident_files"))
        payment_log = self.client.get(reverse("payment_log"))

        self.assertContains(resident_files, "Assigned Resident")
        self.assertNotContains(resident_files, "Other Resident")
        self.assertContains(payment_log, "Assigned Resident")
        self.assertNotContains(payment_log, "Other Resident")

    def test_resident_files_hide_unconverted_applications(self):
        landlord = User.objects.create_user(
            username="resident-files-filter-landlord",
            email="resident-files-filter@example.com",
            password="StrongPass123!",
            role="landlord",
            is_staff=True,
        )
        resident_user = User.objects.create_user(
            username="converted-resident-user",
            email="converted@example.com",
            password="StrongPass123!",
            role="tenant",
        )
        property_obj = Property.objects.create(name="Resident Files Filter Property", landlord_email=landlord.email)
        HousingApplication.objects.create(
            property=property_obj,
            full_name="Applicant Only",
            phone="555-0550",
            email="applicant-only@example.com",
            age=34,
            income_source="Employment",
            monthly_income=Decimal("2800.00"),
            housing_need="Needs housing.",
        )
        HousingApplication.objects.create(
            property=property_obj,
            user=resident_user,
            full_name="Converted Resident",
            phone="555-0551",
            email="converted@example.com",
            age=42,
            income_source="Employment",
            monthly_income=Decimal("3000.00"),
            housing_need="Current resident.",
        )

        self.client.login(username="resident-files-filter-landlord", password="StrongPass123!")
        resident_files = self.client.get(reverse("landlord_resident_files"))
        attention = self.client.get(reverse("landlord_attention"))

        self.assertContains(resident_files, "Converted Resident")
        self.assertNotContains(resident_files, "Applicant Only")
        self.assertContains(attention, "Applicant Only")

    def test_superadmin_resident_inspection_hides_unconverted_applications(self):
        superuser = User.objects.create_user(
            username="resident-inspection-superadmin",
            email="resident-inspection-superadmin@example.com",
            password="StrongPass123!",
            role="admin",
            is_staff=True,
        )
        resident_user = User.objects.create_user(
            username="resident-inspection-tenant",
            email="resident-inspection-tenant@example.com",
            password="StrongPass123!",
            role="tenant",
        )
        property_obj = Property.objects.create(name="Superadmin Resident Inspection Property")
        HousingApplication.objects.create(
            property=property_obj,
            full_name="Inspection Applicant Only",
            phone="555-0552",
            email="inspection-applicant@example.com",
            age=34,
            income_source="Employment",
            monthly_income=Decimal("2800.00"),
            housing_need="Needs housing.",
        )
        HousingApplication.objects.create(
            property=property_obj,
            user=resident_user,
            full_name="Inspection Resident File",
            phone="555-0553",
            email="resident-inspection-tenant@example.com",
            age=42,
            income_source="Employment",
            monthly_income=Decimal("3000.00"),
            housing_need="Current resident.",
        )

        self.client.login(username="resident-inspection-superadmin", password="StrongPass123!")
        response = self.client.get(reverse("superadmin_residents"))

        self.assertContains(response, "Inspection Resident File")
        self.assertNotContains(response, "Inspection Applicant Only")

    def test_staff_can_edit_resident_balances_directly(self):
        landlord = User.objects.create_user(
            username="balance-edit-landlord",
            email="balance-edit-landlord@example.com",
            password="StrongPass123!",
            role="landlord",
            is_staff=True,
        )
        resident_user = User.objects.create_user(
            username="balance-edit-tenant",
            email="balance-edit-tenant@example.com",
            password="StrongPass123!",
            role="tenant",
        )
        property_obj = Property.objects.create(name="Balance Edit Property", landlord_email=landlord.email)
        resident = HousingApplication.objects.create(
            property=property_obj,
            user=resident_user,
            full_name="Balance Edit Resident",
            phone="555-0554",
            email="balance-edit-tenant@example.com",
            age=42,
            income_source="Employment",
            monthly_income=Decimal("3000.00"),
            housing_need="Current resident.",
            monthly_rent=Decimal("650.00"),
            balance=Decimal("650.00"),
            utility_monthly=Decimal("55.00"),
            utility_balance=Decimal("55.00"),
            deposit_required=Decimal("450.00"),
            deposit_paid=Decimal("95.00"),
        )

        self.client.login(username="balance-edit-landlord", password="StrongPass123!")
        response = self.client.post(reverse("edit_resident_balances", args=[resident.id]), {
            "monthly_rent": "650.00",
            "balance": "325.00",
            "utility_monthly": "55.00",
            "utility_balance": "0.00",
            "deposit_required": "450.00",
            "deposit_paid": "450.00",
            "rent_due_day": "1",
        })

        self.assertRedirects(response, reverse("landlord_resident_files"))
        resident.refresh_from_db()
        self.assertEqual(resident.balance, Decimal("325.00"))
        self.assertEqual(resident.utility_balance, Decimal("0.00"))
        self.assertEqual(resident.deposit_paid, Decimal("450.00"))

    def test_staff_cannot_edit_unconverted_applicant_balances(self):
        landlord = User.objects.create_user(
            username="balance-edit-applicant-landlord",
            email="balance-edit-applicant@example.com",
            password="StrongPass123!",
            role="landlord",
            is_staff=True,
        )
        property_obj = Property.objects.create(name="Balance Edit Applicant Property", landlord_email=landlord.email)
        applicant = HousingApplication.objects.create(
            property=property_obj,
            full_name="Balance Edit Applicant",
            phone="555-0555",
            email="balance-edit-applicant@example.com",
            age=34,
            income_source="Employment",
            monthly_income=Decimal("2800.00"),
            housing_need="Needs housing.",
        )

        self.client.login(username="balance-edit-applicant-landlord", password="StrongPass123!")
        response = self.client.get(reverse("edit_resident_balances", args=[applicant.id]))

        self.assertEqual(response.status_code, 404)

    def test_landlord_dashboard_lists_current_month_rent_and_utility_exceptions(self):
        landlord = User.objects.create_user(
            username="collection-landlord",
            email="collection@example.com",
            password="StrongPass123!",
            role="landlord",
            is_staff=True,
        )
        assigned_property = Property.objects.create(name="Collection Property", landlord_email=landlord.email)
        other_property = Property.objects.create(name="Other Collection Property", landlord_email="other@example.com")
        paid_user = User.objects.create_user(username="paid-collection-user", password="StrongPass123!", role="tenant")
        missing_utility_user = User.objects.create_user(username="missing-utility-user", password="StrongPass123!", role="tenant")
        other_user = User.objects.create_user(username="other-missing-user", password="StrongPass123!", role="tenant")
        paid_resident = HousingApplication.objects.create(
            property=assigned_property,
            user=paid_user,
            full_name="Paid Resident",
            phone="555-0301",
            email="paid-collection@example.com",
            age=51,
            space_label="A",
            monthly_rent=Decimal("500.00"),
            utility_monthly=Decimal("66.00"),
            income_source="Employment",
            monthly_income=Decimal("2500.00"),
            housing_need="Current resident.",
        )
        missing_utility_resident = HousingApplication.objects.create(
            property=assigned_property,
            user=missing_utility_user,
            full_name="Missing Utility Resident",
            phone="555-0302",
            email="missing-utility@example.com",
            age=52,
            space_label="B",
            monthly_rent=Decimal("500.00"),
            utility_monthly=Decimal("66.00"),
            income_source="Employment",
            monthly_income=Decimal("2500.00"),
            housing_need="Current resident.",
        )
        other_resident = HousingApplication.objects.create(
            property=other_property,
            user=other_user,
            full_name="Other Missing Resident",
            phone="555-0303",
            email="other-missing@example.com",
            age=53,
            space_label="C",
            monthly_rent=Decimal("500.00"),
            utility_monthly=Decimal("66.00"),
            income_source="Employment",
            monthly_income=Decimal("2500.00"),
            housing_need="Current resident.",
        )
        Payment.objects.create(application=paid_resident, payment_type="rent", amount=Decimal("500.00"), status="completed")
        Payment.objects.create(application=paid_resident, payment_type="utility", amount=Decimal("66.00"), status="completed")
        Payment.objects.create(application=missing_utility_resident, payment_type="rent", amount=Decimal("500.00"), status="completed")

        self.client.login(username="collection-landlord", password="StrongPass123!")

        response = self.client.get(reverse("landlord_dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Monthly Collection Watch")
        self.assertContains(response, "Missing Utility Resident")
        self.assertContains(response, "Utilities")
        self.assertNotContains(response, "Paid Resident</td>")
        self.assertNotContains(response, "Other Missing Resident")

    def test_landlord_collection_watch_cleans_room_prefix(self):
        landlord = User.objects.create_user(
            username="collection-room-landlord",
            email="collection-room@example.com",
            password="StrongPass123!",
            role="landlord",
            is_staff=True,
        )
        property_obj = Property.objects.create(name="Collection Room Property", landlord_email=landlord.email)
        resident_user = User.objects.create_user(username="collection-room-user", password="StrongPass123!", role="tenant")
        HousingApplication.objects.create(
            property=property_obj,
            user=resident_user,
            full_name="Room Prefix Resident",
            phone="555-0310",
            email="collection-room-resident@example.com",
            age=51,
            space_type="Room",
            space_label="Room J",
            monthly_rent=Decimal("500.00"),
            utility_monthly=Decimal("55.00"),
            income_source="Employment",
            monthly_income=Decimal("2500.00"),
            housing_need="Current resident.",
        )

        self.client.login(username="collection-room-landlord", password="StrongPass123!")
        response = self.client.get(reverse("landlord_dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "<td>J</td>", html=True)
        self.assertNotContains(response, "<td>Room J</td>", html=True)

    def test_attention_count_drops_when_items_are_opened(self):
        landlord = User.objects.create_user(
            username="attention-landlord",
            email="attention-landlord@example.com",
            password="StrongPass123!",
            role="landlord",
            is_staff=True,
        )
        property_obj = Property.objects.create(name="Attention Property", landlord_email=landlord.email)
        resident_user = User.objects.create_user(username="attention-resident", password="StrongPass123!", role="tenant")
        applicant = HousingApplication.objects.create(
            property=property_obj,
            full_name="Attention Applicant",
            phone="555-0320",
            email="attention-applicant@example.com",
            age=42,
            income_source="Employment",
            monthly_income=Decimal("2500.00"),
            housing_need="Needs housing.",
        )
        resident = HousingApplication.objects.create(
            property=property_obj,
            user=resident_user,
            full_name="Attention Resident",
            phone="555-0321",
            email="attention-resident@example.com",
            age=43,
            income_source="Employment",
            monthly_income=Decimal("2500.00"),
            housing_need="Current resident.",
        )
        intake = ExistingResidentIntake.objects.create(
            property=property_obj,
            first_name="Setup",
            last_name="Resident",
            email="setup-resident@example.com",
            phone="555-0322",
        )
        resident_message = ResidentMessage.objects.create(
            application=resident,
            subject="Attention message",
            message="Please review.",
            message_type="general",
            status="submitted",
        )
        document = ApplicantDocument.objects.create(
            application=resident,
            document_type="other",
            file=SimpleUploadedFile("attention.txt", b"hello", content_type="text/plain"),
            name="Attention Document",
            status="uploaded",
            landlord_notified=False,
        )

        self.client.login(username="attention-landlord", password="StrongPass123!")
        response = self.client.get(reverse("landlord_dashboard"))
        self.assertEqual(response.context["attention_count"], 4)

        self.client.get(reverse("application_detail", args=[applicant.id]))
        applicant.refresh_from_db()
        self.assertIsNotNone(applicant.landlord_reviewed_at)
        response = self.client.get(reverse("landlord_dashboard"))
        self.assertEqual(response.context["attention_count"], 3)

        self.client.get(reverse("landlord_existing_resident_intake_detail", args=[intake.id]))
        intake.refresh_from_db()
        self.assertIsNotNone(intake.landlord_reviewed_at)
        response = self.client.get(reverse("landlord_dashboard"))
        self.assertEqual(response.context["attention_count"], 2)

        self.client.get(reverse("landlord_message_detail", args=[resident_message.id]))
        resident_message.refresh_from_db()
        self.assertEqual(resident_message.status, "reviewed")
        response = self.client.get(reverse("landlord_dashboard"))
        self.assertEqual(response.context["attention_count"], 1)

        self.client.get(reverse("open_applicant_document", args=[document.id]))
        document.refresh_from_db()
        self.assertTrue(document.landlord_notified)
        response = self.client.get(reverse("landlord_dashboard"))
        self.assertEqual(response.context["attention_count"], 0)

    def test_rent_roll_is_resident_only_month_labeled_and_room_sorted(self):
        landlord = User.objects.create_user(
            username="rent-roll-landlord",
            email="rent-roll-landlord@example.com",
            password="StrongPass123!",
            role="landlord",
            is_staff=True,
        )
        property_obj = Property.objects.create(name="Rent Roll Property", landlord_email=landlord.email)
        room_b_user = User.objects.create_user(username="room-b-user", password="StrongPass123!", role="tenant")
        room_a_user = User.objects.create_user(username="room-a-user", password="StrongPass123!", role="tenant")
        room_c_user = User.objects.create_user(username="room-c-user", password="StrongPass123!", role="tenant")
        room_b_resident = HousingApplication.objects.create(
            property=property_obj,
            user=room_b_user,
            full_name="Room B Resident",
            phone="555-0601",
            email="room-b@example.com",
            age=41,
            space_label="Room B",
            monthly_rent=Decimal("600.00"),
            balance=Decimal("600.00"),
            utility_monthly=Decimal("55.00"),
            utility_balance=Decimal("55.00"),
            deposit_required=Decimal("450.00"),
            deposit_paid=Decimal("200.00"),
            income_source="Employment",
            monthly_income=Decimal("2500.00"),
            housing_need="Current resident.",
        )
        HousingApplication.objects.create(
            property=property_obj,
            user=room_a_user,
            full_name="Room A Resident",
            phone="555-0602",
            email="room-a@example.com",
            age=42,
            space_label="A",
            monthly_rent=Decimal("650.00"),
            income_source="Employment",
            monthly_income=Decimal("2500.00"),
            housing_need="Current resident.",
        )
        HousingApplication.objects.create(
            property=property_obj,
            user=room_c_user,
            full_name="Room C Resident",
            phone="555-0603",
            email="room-c@example.com",
            age=43,
            space_label="C",
            monthly_rent=Decimal("625.00"),
            income_source="Employment",
            monthly_income=Decimal("2500.00"),
            housing_need="Current resident.",
        )
        HousingApplication.objects.create(
            property=property_obj,
            full_name="Applicant Should Not Show",
            phone="555-0604",
            email="applicant-rent-roll@example.com",
            age=44,
            space_label="D",
            monthly_rent=Decimal("700.00"),
            income_source="Employment",
            monthly_income=Decimal("2500.00"),
            housing_need="Applicant only.",
        )
        Payment.objects.create(
            application=room_b_resident,
            payment_type="rent",
            amount=Decimal("300.00"),
            status="completed",
            service_month=date(2026, 6, 1),
        )

        self.client.login(username="rent-roll-landlord", password="StrongPass123!")
        response = self.client.get(f"{reverse('rent_roll')}?month=2026-06")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "June 2026")
        self.assertContains(response, "Rent Roll Property")
        self.assertContains(response, "Deposit Paid")
        self.assertContains(response, "Deposit Balance")
        self.assertContains(response, "Rent Paid")
        self.assertNotContains(response, "<th>Property</th>", html=True)
        self.assertNotContains(response, "Rent Paid This Month")
        self.assertNotContains(response, "Applicant Should Not Show")

        content = response.content.decode()
        self.assertLess(content.index('class="unit-col">A</td>'), content.index('class="unit-col">B</td>'))
        self.assertLess(content.index('class="unit-col">B</td>'), content.index('class="unit-col">C</td>'))
        self.assertContains(response, "$300.00")
        self.assertContains(response, "$250.00")
        self.assertEqual(response.context["totals"]["monthly_rent"], Decimal("1875.00"))
        self.assertEqual(response.context["totals"]["rent_paid"], Decimal("300.00"))
        self.assertEqual(response.context["totals"]["rent_balance"], Decimal("1575.00"))
        self.assertEqual(response.context["totals"]["utility_monthly"], Decimal("187.00"))
        self.assertEqual(response.context["totals"]["deposit_required"], Decimal("1350.00"))
        self.assertContains(response, "<td>Total</td>", html=True)
        self.assertContains(response, "Print Report")
        self.assertContains(response, "window.print()")
        self.assertContains(response, "size: landscape")
        self.assertContains(response, "table-layout: fixed")

    def test_rent_roll_prompts_for_property_when_multiple_properties_exist(self):
        superuser = User.objects.create_user(
            username="rent-roll-super",
            email="rent-roll-super@example.com",
            password="StrongPass123!",
            role="admin",
            is_staff=True,
            is_superuser=True,
        )
        first_property = Property.objects.create(name="First Rent Roll Property")
        second_property = Property.objects.create(name="Second Rent Roll Property")
        first_user = User.objects.create_user(username="first-rent-roll-user", password="StrongPass123!", role="tenant")
        second_user = User.objects.create_user(username="second-rent-roll-user", password="StrongPass123!", role="tenant")
        first_resident = HousingApplication.objects.create(
            property=first_property,
            user=first_user,
            full_name="First Rent Roll Resident",
            phone="555-0610",
            email="first-roll@example.com",
            age=45,
            space_label="A",
            monthly_rent=Decimal("500.00"),
            income_source="Employment",
            monthly_income=Decimal("2500.00"),
            housing_need="Current resident.",
        )
        second_resident = HousingApplication.objects.create(
            property=second_property,
            user=second_user,
            full_name="Second Rent Roll Resident",
            phone="555-0611",
            email="second-roll@example.com",
            age=46,
            space_label="B",
            monthly_rent=Decimal("600.00"),
            income_source="Employment",
            monthly_income=Decimal("2500.00"),
            housing_need="Current resident.",
        )

        self.client.login(username="rent-roll-super", password="StrongPass123!")
        picker_response = self.client.get(reverse("rent_roll"))

        self.assertEqual(picker_response.status_code, 200)
        self.assertTrue(picker_response.context["show_property_picker"])
        self.assertContains(picker_response, "Choose A Property")
        self.assertContains(picker_response, "First Rent Roll Property")
        self.assertContains(picker_response, "Second Rent Roll Property")

        property_response = self.client.get(f"{reverse('rent_roll')}?property_id={second_property.id}")

        self.assertFalse(property_response.context["show_property_picker"])
        self.assertEqual(property_response.context["selected_property"], second_property)
        self.assertContains(property_response, second_resident.full_name)
        self.assertNotContains(property_response, first_resident.full_name)

    def test_rent_roll_csv_matches_resident_only_month_view(self):
        landlord = User.objects.create_user(
            username="rent-roll-csv-landlord",
            email="rent-roll-csv-landlord@example.com",
            password="StrongPass123!",
            role="landlord",
            is_staff=True,
        )
        property_obj = Property.objects.create(name="Rent Roll CSV Property", landlord_email=landlord.email)
        tenant_user = User.objects.create_user(username="rent-roll-csv-tenant", password="StrongPass123!", role="tenant")
        resident = HousingApplication.objects.create(
            property=property_obj,
            user=tenant_user,
            full_name="CSV Resident",
            phone="555-0605",
            email="csv-resident@example.com",
            age=45,
            space_label="Room G",
            monthly_rent=Decimal("560.00"),
            balance=Decimal("560.00"),
            utility_monthly=Decimal("55.00"),
            utility_balance=Decimal("55.00"),
            income_source="Employment",
            monthly_income=Decimal("2500.00"),
            housing_need="Current resident.",
        )
        HousingApplication.objects.create(
            property=property_obj,
            full_name="CSV Applicant",
            phone="555-0606",
            email="csv-applicant@example.com",
            age=46,
            monthly_rent=Decimal("700.00"),
            income_source="Employment",
            monthly_income=Decimal("2500.00"),
            housing_need="Applicant only.",
        )
        Payment.objects.create(
            application=resident,
            payment_type="utility",
            amount=Decimal("55.00"),
            status="completed",
            service_month=date(2026, 6, 1),
        )

        self.client.login(username="rent-roll-csv-landlord", password="StrongPass123!")
        response = self.client.get(f"{reverse('export_rent_roll_csv')}?month=2026-06")
        content = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertIn("June 2026,CSV Resident,G", content)
        self.assertIn("Utilities Paid", content)
        self.assertIn("June 2026,TOTAL,,560.00,0.00,560.00,55.00,55.00,0.00,450.00,0.00,450.00", content)
        self.assertNotIn("Property", content.splitlines()[0])
        self.assertNotIn("Utilities Paid This Month", content)
        self.assertNotIn("CSV Applicant", content)

    def test_t12_and_payment_log_have_print_actions(self):
        landlord = User.objects.create_user(
            username="print-report-landlord",
            email="print-report@example.com",
            password="StrongPass123!",
            role="landlord",
            is_staff=True,
        )
        property_obj = Property.objects.create(name="Print Report Property", landlord_email=landlord.email)
        tenant_user = User.objects.create_user(username="print-report-tenant", password="StrongPass123!", role="tenant")
        resident = HousingApplication.objects.create(
            property=property_obj,
            user=tenant_user,
            full_name="Print Report Resident",
            phone="555-0710",
            email="print-resident@example.com",
            age=45,
            space_label="A",
            monthly_rent=Decimal("560.00"),
            income_source="Employment",
            monthly_income=Decimal("2500.00"),
            housing_need="Current resident.",
        )
        Payment.objects.create(
            application=resident,
            payment_type="rent",
            amount=Decimal("560.00"),
            status="completed",
            service_month=date(2026, 6, 1),
        )

        self.client.login(username="print-report-landlord", password="StrongPass123!")
        t12_response = self.client.get(reverse("t12_report"))
        payment_response = self.client.get(reverse("payment_log"))

        self.assertContains(t12_response, "Print Report")
        self.assertContains(t12_response, "window.print()")
        self.assertContains(t12_response, "size: landscape")
        self.assertContains(t12_response, "table-layout: fixed")
        self.assertContains(payment_response, "Print Report")
        self.assertContains(payment_response, "window.print()")
        self.assertContains(payment_response, "size: landscape")
        self.assertContains(payment_response, "table-layout: fixed")

    def test_payment_log_orders_months_chronologically(self):
        landlord = User.objects.create_user(
            username="payment-month-order-landlord",
            email="payment-month-order@example.com",
            password="StrongPass123!",
            role="landlord",
            is_staff=True,
        )
        property_obj = Property.objects.create(name="Payment Month Order Property", landlord_email=landlord.email)
        resident_user = User.objects.create_user(username="payment-month-order-tenant", password="StrongPass123!", role="tenant")
        resident = HousingApplication.objects.create(
            property=property_obj,
            user=resident_user,
            full_name="Payment Month Order Resident",
            phone="555-0711",
            email="month-order@example.com",
            age=45,
            space_label="B",
            monthly_rent=Decimal("506.00"),
            income_source="Employment",
            monthly_income=Decimal("2500.00"),
            housing_need="Current resident.",
        )
        for service_month in [date(2026, 4, 1), date(2026, 3, 1), date(2026, 2, 1), date(2026, 1, 1), date(2026, 5, 1), date(2026, 6, 1)]:
            Payment.objects.create(
                application=resident,
                payment_type="rent",
                amount=Decimal("506.00"),
                status="completed",
                service_month=service_month,
            )

        self.client.login(username="payment-month-order-landlord", password="StrongPass123!")
        response = self.client.get(reverse("payment_log"))
        months = response.context["payment_log"][0]["months"]

        self.assertEqual(
            [month["month_label"] for month in months],
            ["January 2026", "February 2026", "March 2026", "April 2026", "May 2026", "June 2026"],
        )

        filtered_response = self.client.get(f"{reverse('payment_log')}?month=2026-05")
        filtered_groups = filtered_response.context["payment_log"][0]["months"]

        self.assertTrue(filtered_response.context["month_filter_active"])
        self.assertContains(filtered_response, "Showing May 2026.")
        self.assertContains(filtered_response, "Choose Month To View Or Print")
        self.assertContains(filtered_response, 'value="2026-05"')
        self.assertContains(filtered_response, "Print May 2026")
        self.assertContains(filtered_response, "All Months")
        self.assertEqual([month["month_label"] for month in filtered_groups], ["May 2026"])
        self.assertNotContains(filtered_response, "January 2026")

        csv_response = self.client.get(f"{reverse('export_payment_log_csv')}?month=2026-05")
        csv_content = csv_response.content.decode()

        self.assertIn('filename="payment_log_2026_05.csv"', csv_response["Content-Disposition"])
        self.assertIn("May 2026", csv_content)
        self.assertNotIn("January 2026", csv_content)

    def test_rent_roll_lists_room_roster_before_profile_setup(self):
        landlord = User.objects.create_user(
            username="rent-roll-roster-landlord",
            email="rent-roll-roster@example.com",
            password="StrongPass123!",
            role="landlord",
            is_staff=True,
        )
        property_obj = Property.objects.create(name="Roster Rent Roll Property", landlord_email=landlord.email)
        PropertyRoomRent.objects.create(
            property=property_obj,
            room_unit_label="Room J",
            monthly_rent=Decimal("561.00"),
            utility_monthly=Decimal("55.00"),
            deposit_required=Decimal("450.00"),
            deposit_paid=Decimal("450.00"),
        )
        CurrentResidentRosterEntry.objects.create(
            property=property_obj,
            first_name="Michael",
            last_name="Dudley",
            email="michael-dudley@example.com",
            room_unit_label="J",
        )
        HousingApplication.objects.create(
            property=property_obj,
            full_name="Applicant Not On Rent Roll",
            phone="555-0610",
            email="applicant-not-rent-roll@example.com",
            age=40,
            space_label="K",
            monthly_rent=Decimal("700.00"),
            income_source="Employment",
            monthly_income=Decimal("2500.00"),
            housing_need="Applicant only.",
        )

        self.client.login(username="rent-roll-roster-landlord", password="StrongPass123!")
        response = self.client.get(f"{reverse('rent_roll')}?month=2026-05")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Michael Dudley")
        self.assertContains(response, '<td class="unit-col">J</td>', html=True)
        self.assertContains(response, "$561.00")
        self.assertContains(response, "$55.00")
        self.assertNotContains(response, "Applicant Not On Rent Roll")

    def test_backfill_monthly_rent_payments_creates_missing_roster_payments(self):
        property_obj = Property.objects.create(name="Backfill Rent Property")
        PropertyRoomRent.objects.create(
            property=property_obj,
            room_unit_label="Room J",
            monthly_rent=Decimal("561.00"),
            utility_monthly=Decimal("55.00"),
        )
        PropertyRoomRent.objects.create(
            property=property_obj,
            room_unit_label="Room N",
            monthly_rent=Decimal("1100.00"),
            utility_monthly=Decimal("55.00"),
        )
        CurrentResidentRosterEntry.objects.create(
            property=property_obj,
            first_name="Michael",
            last_name="Dudley",
            email="michael@example.com",
            room_unit_label="J",
        )
        CurrentResidentRosterEntry.objects.create(
            property=property_obj,
            first_name="Hero",
            last_name="Lowe",
            email="hero@example.com",
            room_unit_label="N",
        )
        out = StringIO()

        call_command(
            "backfill_monthly_rent_payments",
            "--property-name",
            "Backfill Rent Property",
            "--month",
            "2026-05",
            "--exclude-room",
            "N",
            "--confirm",
            stdout=out,
        )

        michael = HousingApplication.objects.get(full_name="Michael Dudley")
        self.assertEqual(michael.space_label, "J")
        self.assertTrue(Payment.objects.filter(
            application=michael,
            payment_type="rent",
            amount=Decimal("561.00"),
            service_month=date(2026, 5, 1),
            status="completed",
        ).exists())
        self.assertFalse(HousingApplication.objects.filter(full_name="Hero Lowe").exists())

        call_command(
            "backfill_monthly_rent_payments",
            "--property-name",
            "Backfill Rent Property",
            "--month",
            "2026-05",
            "--exclude-room",
            "N",
            "--confirm",
            stdout=StringIO(),
        )
        self.assertEqual(Payment.objects.filter(application=michael, payment_type="rent").count(), 1)

    def test_backfill_monthly_payments_can_create_utilities_only(self):
        property_obj = Property.objects.create(name="Backfill Utility Property")
        PropertyRoomRent.objects.create(
            property=property_obj,
            room_unit_label="J",
            monthly_rent=Decimal("561.00"),
            utility_monthly=Decimal("55.00"),
        )
        CurrentResidentRosterEntry.objects.create(
            property=property_obj,
            first_name="Michael",
            last_name="Dudley",
            email="michael@example.com",
            room_unit_label="J",
        )

        call_command(
            "backfill_monthly_rent_payments",
            "--property-name",
            "Backfill Utility Property",
            "--month",
            "2026-05",
            "--payment-type",
            "utility",
            "--confirm",
            stdout=StringIO(),
        )

        michael = HousingApplication.objects.get(full_name="Michael Dudley")
        self.assertFalse(Payment.objects.filter(application=michael, payment_type="rent").exists())
        self.assertTrue(Payment.objects.filter(
            application=michael,
            payment_type="utility",
            amount=Decimal("55.00"),
            service_month=date(2026, 5, 1),
            status="completed",
        ).exists())

    def test_move_payment_service_month_corrects_early_payment(self):
        property_obj = Property.objects.create(name="Move Payment Month Property")
        resident = HousingApplication.objects.create(
            property=property_obj,
            full_name="Grady Bradley",
            phone="555-0620",
            email="grady@example.com",
            age=50,
            space_label="B",
            monthly_rent=Decimal("506.00"),
            income_source="Employment",
            monthly_income=Decimal("2500.00"),
            housing_need="Current resident.",
        )
        payment = Payment.objects.create(
            application=resident,
            payment_type="rent",
            payment_method="cash",
            amount=Decimal("506.00"),
            status="completed",
            received_at=timezone.make_aware(datetime(2026, 5, 27, 12, 0)),
        )

        call_command(
            "move_payment_service_month",
            "--property-name",
            "Move Payment Month Property",
            "--from-month",
            "2026-05",
            "--to-month",
            "2026-06",
            "--room",
            "B",
            "--resident-name",
            "Grady",
            "--confirm",
            stdout=StringIO(),
        )

        payment.refresh_from_db()
        self.assertEqual(payment.service_month, date(2026, 6, 1))

    def test_backfill_counts_legacy_received_month_payment_without_duplicate(self):
        property_obj = Property.objects.create(name="Legacy Received Month Property")
        PropertyRoomRent.objects.create(
            property=property_obj,
            room_unit_label="B",
            monthly_rent=Decimal("506.00"),
        )
        resident = HousingApplication.objects.create(
            property=property_obj,
            full_name="Legacy Paid Resident",
            phone="555-0621",
            email="legacy@example.com",
            age=51,
            space_label="B",
            monthly_rent=Decimal("506.00"),
            income_source="Employment",
            monthly_income=Decimal("2500.00"),
            housing_need="Current resident.",
        )
        Payment.objects.create(
            application=resident,
            payment_type="rent",
            payment_method="cash",
            amount=Decimal("506.00"),
            status="completed",
            received_at=timezone.make_aware(datetime(2026, 5, 15, 12, 0)),
        )

        call_command(
            "backfill_monthly_rent_payments",
            "--property-name",
            "Legacy Received Month Property",
            "--month",
            "2026-05",
            "--confirm",
            stdout=StringIO(),
        )

        self.assertEqual(Payment.objects.filter(application=resident, payment_type="rent").count(), 1)

    def test_move_in_month_uses_prorated_rent_for_reports_and_backfill(self):
        landlord = User.objects.create_user(
            username="move-in-prorate-landlord",
            email="move-in-prorate@example.com",
            password="StrongPass123!",
            role="landlord",
            is_staff=True,
        )
        property_obj = Property.objects.create(name="Move In Prorate Property", landlord_email=landlord.email)
        tenant_user = User.objects.create_user(username="move-in-prorate-user", password="StrongPass123!", role="tenant")
        resident = HousingApplication.objects.create(
            property=property_obj,
            user=tenant_user,
            full_name="Move In Resident",
            phone="555-0622",
            email="move-in@example.com",
            age=52,
            space_label="H",
            monthly_rent=Decimal("650.00"),
            balance=Decimal("0.00"),
            lease_start_date=date(2026, 5, 27),
            move_in_rent_charge=Decimal("104.84"),
            utility_monthly=Decimal("55.00"),
            move_in_utility_charge=Decimal("8.87"),
            income_source="Employment",
            monthly_income=Decimal("2500.00"),
            housing_need="Current resident.",
        )
        PropertyRoomRent.objects.create(
            property=property_obj,
            room_unit_label="H",
            monthly_rent=Decimal("650.00"),
            utility_monthly=Decimal("55.00"),
        )
        Payment.objects.create(
            application=resident,
            payment_type="rent",
            payment_method="cash",
            amount=Decimal("104.84"),
            status="completed",
            service_month=date(2026, 5, 1),
        )
        Payment.objects.create(
            application=resident,
            payment_type="utility",
            payment_method="cash",
            amount=Decimal("8.87"),
            status="completed",
            service_month=date(2026, 5, 1),
        )
        current_month = timezone.localdate().replace(day=1)
        if current_month != date(2026, 5, 1):
            Payment.objects.create(
                application=resident,
                payment_type="rent",
                payment_method="cash",
                amount=resident.monthly_rent,
                status="completed",
                service_month=current_month,
            )
            Payment.objects.create(
                application=resident,
                payment_type="utility",
                payment_method="cash",
                amount=resident.utility_monthly,
                status="completed",
                service_month=current_month,
            )

        self.client.login(username="move-in-prorate-landlord", password="StrongPass123!")
        rent_roll_response = self.client.get(f"{reverse('rent_roll')}?month=2026-05")
        dashboard_response = self.client.get(reverse("landlord_dashboard"))

        resident_row = next(row for row in rent_roll_response.context["rows"] if row["resident"] == "Move In Resident")
        self.assertEqual(resident_row["rent_balance"], Decimal("0.00"))
        self.assertEqual(resident_row["utility_balance"], Decimal("0.00"))
        self.assertFalse(
            any(row["application"] == resident for row in dashboard_response.context["collection_watch_rows"])
        )

        out = StringIO()
        call_command(
            "backfill_monthly_rent_payments",
            "--property-name",
            "Move In Prorate Property",
            "--month",
            "2026-05",
            stdout=out,
        )

        self.assertIn("rent already paid", out.getvalue())
        self.assertNotIn("CREATE | Room H | Move In Resident | rent", out.getvalue())

    def test_custom_phone_report_scopes_to_landlord_property(self):
        landlord = User.objects.create_user(
            username="report-landlord",
            email="report-landlord@example.com",
            password="StrongPass123!",
            role="landlord",
            is_staff=True,
        )
        assigned_property = Property.objects.create(name="Report Property", landlord_email=landlord.email)
        other_property = Property.objects.create(name="Other Report Property", landlord_email="other@example.com")
        HousingApplication.objects.create(
            property=assigned_property,
            full_name="Report Resident",
            phone="5550113344",
            email="report-resident@example.com",
            age=51,
            income_source="Employment",
            monthly_income=Decimal("2500.00"),
            housing_need="Current resident.",
        )
        HousingApplication.objects.create(
            property=other_property,
            full_name="Hidden Resident",
            phone="5550113355",
            email="hidden-resident@example.com",
            age=52,
            income_source="Employment",
            monthly_income=Decimal("2500.00"),
            housing_need="Current resident.",
        )

        self.client.login(username="report-landlord", password="StrongPass123!")

        response = self.client.get(reverse("custom_reports"), {
            "report_type": "resident_phone_list",
            "property_id": assigned_property.id,
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Resident Phone List")
        self.assertContains(response, "Report Resident")
        self.assertContains(response, "(555) 011-3344")
        self.assertNotContains(response, "Hidden Resident")

    def test_custom_reports_scope_to_property_owner_and_block_residents(self):
        owner = User.objects.create_user(
            username="report-owner",
            email="owner-report@example.com",
            password="StrongPass123!",
            role="property_owner",
        )
        resident_user = User.objects.create_user(
            username="report-resident-user",
            email="report-resident-user@example.com",
            password="StrongPass123!",
            role="tenant",
        )
        owned_property = Property.objects.create(name="Owner Report Property", owner_email=owner.email)
        other_property = Property.objects.create(name="Different Owner Property", owner_email="different@example.com")
        HousingApplication.objects.create(
            property=owned_property,
            full_name="Owned Property Resident",
            phone="5550114455",
            email="owned-resident@example.com",
            age=51,
            income_source="Employment",
            monthly_income=Decimal("2500.00"),
            housing_need="Current resident.",
        )
        HousingApplication.objects.create(
            property=other_property,
            full_name="Different Owner Resident",
            phone="5550114466",
            email="different-owner-resident@example.com",
            age=52,
            income_source="Employment",
            monthly_income=Decimal("2500.00"),
            housing_need="Current resident.",
        )

        self.client.login(username="report-owner", password="StrongPass123!")

        response = self.client.get(reverse("custom_reports"), {
            "report_type": "resident_phone_list",
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Owned Property Resident")
        self.assertNotContains(response, "Different Owner Resident")

        self.client.logout()
        self.client.login(username="report-resident-user", password="StrongPass123!")

        response = self.client.get(reverse("custom_reports"), {
            "report_type": "resident_phone_list",
        })

        self.assertEqual(response.status_code, 302)

    def test_custom_financial_report_can_mix_expense_types_and_print(self):
        superuser = User.objects.create_user(
            username="report-admin",
            email="report-admin@example.com",
            password="StrongPass123!",
            role="admin",
            is_staff=True,
        )
        property_obj = Property.objects.create(name="Expense Report Property")
        upload = FinancialUpload.objects.create(
            name="May Accounting Export",
            file=SimpleUploadedFile("may.csv", b"category,amount\n", content_type="text/csv"),
        )
        FinancialEntry.objects.create(
            upload=upload,
            property_name=property_obj.name,
            sheet_name="Expenses",
            row_number=1,
            year=2026,
            month=5,
            entry_type="operating_expense",
            category="Repairs",
            description="Plumbing repair",
            amount=Decimal("125.00"),
        )
        FinancialEntry.objects.create(
            upload=upload,
            property_name=property_obj.name,
            sheet_name="Expenses",
            row_number=2,
            year=2026,
            month=5,
            entry_type="capital_expense",
            category="Improvements",
            description="Floor replacement",
            amount=Decimal("400.00"),
        )
        FinancialEntry.objects.create(
            upload=upload,
            property_name=property_obj.name,
            sheet_name="Income",
            row_number=3,
            year=2026,
            month=5,
            entry_type="income",
            category="Rent",
            description="May rent",
            amount=Decimal("900.00"),
        )

        self.client.login(username="report-admin", password="StrongPass123!")

        response = self.client.get(reverse("custom_reports"), {
            "report_type": "financial_entries",
            "property_id": property_obj.id,
            "financial_entry_types": ["operating_expense", "capital_expense"],
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Financial Entries / Expenses")
        self.assertContains(response, "Plumbing repair")
        self.assertContains(response, "Floor replacement")
        self.assertContains(response, "$525.00")
        self.assertContains(response, "size: landscape")
        self.assertContains(response, "table-layout: fixed")
        self.assertNotContains(response, "May rent")

    def test_custom_resident_directory_cross_references_files_and_roster(self):
        owner = User.objects.create_user(
            username="directory-owner",
            email="directory-owner@example.com",
            password="StrongPass123!",
            role="property_owner",
        )
        property_obj = Property.objects.create(name="Directory Property", owner_email=owner.email)
        hidden_property = Property.objects.create(name="Hidden Directory Property", owner_email="hidden@example.com")
        HousingApplication.objects.create(
            property=property_obj,
            full_name="Directory Resident",
            phone="5550117788",
            email="directory-resident@example.com",
            age=38,
            space_label="7",
            lease_start_date=date(2026, 1, 15),
            monthly_rent=Decimal("1250.00"),
            utility_monthly=Decimal("75.00"),
            balance=Decimal("100.00"),
            utility_balance=Decimal("25.00"),
            deposit_paid=Decimal("600.00"),
            income_source="Employment",
            monthly_income=Decimal("4000.00"),
            housing_need="Current resident.",
        )
        CurrentResidentRosterEntry.objects.create(
            property=property_obj,
            first_name="Roster",
            last_name="Only",
            phone="5550117799",
            email="roster-only@example.com",
            room_unit_label="8",
            monthly_rent=Decimal("1150.00"),
            monthly_utilities=Decimal("65.00"),
            deposit_held=Decimal("500.00"),
            last_month_rent_paid=True,
        )
        CurrentResidentRosterEntry.objects.create(
            property=hidden_property,
            first_name="Hidden",
            last_name="Roster",
            room_unit_label="9",
            monthly_rent=Decimal("9999.00"),
        )

        self.client.login(username="directory-owner", password="StrongPass123!")
        response = self.client.get(reverse("custom_reports"), {
            "report_type": "resident_directory",
            "property_id": property_obj.id,
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Resident Directory / Roster Export")
        self.assertContains(response, "Directory Resident")
        self.assertContains(response, "(555) 011-7788")
        self.assertContains(response, "roster-only@example.com")
        self.assertContains(response, "Uploaded Roster")
        self.assertContains(response, "$2400.00")
        self.assertContains(response, "Download CSV")
        self.assertNotContains(response, "Hidden Roster")

        csv_response = self.client.get(reverse("custom_reports"), {
            "report_type": "resident_directory",
            "property_id": property_obj.id,
            "export": "csv",
        })

        self.assertEqual(csv_response.status_code, 200)
        self.assertEqual(csv_response["Content-Type"], "text/csv")
        csv_content = csv_response.content.decode()
        self.assertIn("Resident Directory / Roster Export", csv_content)
        self.assertIn("Directory Resident", csv_content)
        self.assertIn("Roster Only", csv_content)
        self.assertNotIn("Hidden Roster", csv_content)

    def test_custom_report_template_saves_and_runs_with_math(self):
        owner = User.objects.create_user(
            username="template-owner",
            email="template-owner@example.com",
            password="StrongPass123!",
            role="property_owner",
        )
        property_obj = Property.objects.create(name="Template Property", owner_email=owner.email)
        category = ExpenseCategory.objects.create(name="Power")
        AccountingReceipt.objects.create(
            property=property_obj,
            vendor="Utility One",
            receipt_file=SimpleUploadedFile("one.txt", b"receipt", content_type="text/plain"),
            receipt_date=date(2026, 5, 1),
            category=category,
            amount=Decimal("100.00"),
            status="approved",
        )
        AccountingReceipt.objects.create(
            property=property_obj,
            vendor="Utility Two",
            receipt_file=SimpleUploadedFile("two.txt", b"receipt", content_type="text/plain"),
            receipt_date=date(2026, 5, 2),
            category=category,
            amount=Decimal("200.00"),
            status="approved",
        )

        self.client.login(username="template-owner", password="StrongPass123!")
        response = self.client.get(reverse("custom_reports"), {
            "report_type": "receipt_expense_detail",
            "property_id": property_obj.id,
            "save_template": "on",
            "template_name": "May Utility Receipts",
            "math_mode": "sum",
            "math_column": "Amount",
        })

        self.assertEqual(response.status_code, 200)
        self.assertTrue(ReportTemplate.objects.filter(created_by=owner, name="May Utility Receipts").exists())
        self.assertContains(response, "Saved Report Templates")
        self.assertContains(response, "Sum of Amount")
        self.assertContains(response, "$300.00")

        template = ReportTemplate.objects.get(created_by=owner, name="May Utility Receipts")
        run_response = self.client.get(reverse("run_custom_report_template", args=[template.id]))
        self.assertEqual(run_response.status_code, 302)
        self.assertIn("receipt_expense_detail", run_response.url)

    def test_custom_vendor_reports_cross_reference_receipts_and_contacts(self):
        owner = User.objects.create_user(
            username="vendor-owner",
            email="vendor-owner@example.com",
            password="StrongPass123!",
            role="property_owner",
        )
        property_obj = Property.objects.create(name="Vendor Property", owner_email=owner.email)
        hidden_property = Property.objects.create(name="Hidden Vendor Property", owner_email="hidden@example.com")
        category = ExpenseCategory.objects.create(name="Maintenance Supplies")
        PropertyUtilityVendor.objects.create(
            property=property_obj,
            service_type="Power",
            provider_name="Pacific Power",
            phone="5550116600",
            setup_url="https://example.com/power",
            notes="Tenant setup link",
        )
        AccountingReceipt.objects.create(
            property=property_obj,
            vendor="Pacific Power",
            receipt_file=SimpleUploadedFile("power.txt", b"receipt", content_type="text/plain"),
            receipt_date=date(2026, 5, 2),
            category=category,
            amount=Decimal("210.00"),
            status="approved",
            description="May power",
        )
        AccountingReceipt.objects.create(
            property=property_obj,
            vendor="Ace Hardware",
            receipt_file=SimpleUploadedFile("ace.txt", b"receipt", content_type="text/plain"),
            receipt_date=date(2026, 5, 4),
            category=category,
            amount=Decimal("45.50"),
            status="needs_review",
            description="Door parts",
        )
        AccountingReceipt.objects.create(
            property=hidden_property,
            vendor="Hidden Vendor",
            receipt_file=SimpleUploadedFile("hidden.txt", b"receipt", content_type="text/plain"),
            receipt_date=date(2026, 5, 4),
            category=category,
            amount=Decimal("999.00"),
        )

        self.client.login(username="vendor-owner", password="StrongPass123!")

        detail = self.client.get(reverse("custom_reports"), {
            "report_type": "receipt_expense_detail",
            "property_id": property_obj.id,
        })
        directory = self.client.get(reverse("custom_reports"), {
            "report_type": "vendor_directory",
            "property_id": property_obj.id,
        })
        summary = self.client.get(reverse("custom_reports"), {
            "report_type": "vendor_category_summary",
            "property_id": property_obj.id,
        })

        self.assertContains(detail, "Receipt Expense Detail")
        self.assertContains(detail, "Door parts")
        self.assertContains(directory, "Vendor Directory")
        self.assertContains(directory, "Pacific Power")
        self.assertContains(directory, "(555) 011-6600")
        self.assertContains(directory, "Ace Hardware")
        self.assertContains(summary, "Vendor / Category Summary")
        self.assertContains(summary, "Maintenance Supplies")
        self.assertContains(summary, "$255.50")
        self.assertNotContains(detail, "Hidden Vendor")
        self.assertNotContains(directory, "Hidden Vendor")
        self.assertNotContains(summary, "Hidden Vendor")

    def test_custom_data_inventory_counts_scoped_property_records(self):
        owner = User.objects.create_user(
            username="inventory-owner",
            email="inventory-owner@example.com",
            password="StrongPass123!",
            role="property_owner",
        )
        property_obj = Property.objects.create(name="Inventory Property", owner_email=owner.email)
        hidden_property = Property.objects.create(name="Hidden Inventory Property", owner_email="hidden@example.com")
        resident = HousingApplication.objects.create(
            property=property_obj,
            full_name="Inventory Resident",
            phone="5550119911",
            email="inventory@example.com",
            age=44,
            income_source="Employment",
            monthly_income=Decimal("3500.00"),
            housing_need="Current resident.",
        )
        HousingApplication.objects.create(
            property=hidden_property,
            full_name="Hidden Inventory Resident",
            phone="5550119922",
            age=44,
            income_source="Employment",
            monthly_income=Decimal("3500.00"),
            housing_need="Current resident.",
        )
        Payment.objects.create(application=resident, payment_type="rent", amount=Decimal("700.00"), status="completed")
        ResidentMessage.objects.create(application=resident, subject="Inventory", message="Inventory message")
        SignedDocument.objects.create(application=resident, document_type="lease", title="Lease")

        self.client.login(username="inventory-owner", password="StrongPass123!")
        response = self.client.get(reverse("custom_reports"), {
            "report_type": "data_inventory",
            "property_id": property_obj.id,
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Property Data Inventory")
        self.assertContains(response, "Inventory Property")
        self.assertNotContains(response, "Hidden Inventory Property")

    def test_demo_reset_refuses_live_mode(self):
        with self.assertRaises(CommandError):
            call_command("reset_demo_environment", "--confirm", stdout=StringIO())

    @override_settings(DEMO_MODE=True, DEMO_ADMIN_USERNAME="demo-admin")
    def test_demo_reset_seeds_temporary_workspace_and_demo_entry(self):
        call_command("reset_demo_environment", "--confirm", stdout=StringIO())

        self.assertTrue(User.objects.filter(username="demo-admin", role="admin").exists())
        self.assertTrue(Property.objects.filter(name="Demo Ridge Apartments").exists())
        self.assertTrue(Property.objects.filter(name="Cedar Market Lofts").exists())
        self.assertTrue(Property.objects.filter(name="Pine Street Villas").exists())
        self.assertTrue(Property.objects.filter(name="Harbor View Senior Living").exists())
        self.assertEqual(Property.objects.count(), 4)
        self.assertEqual(HousingApplication.objects.filter(property__name="Demo Ridge Apartments").count(), 14)
        self.assertEqual(HousingApplication.objects.count(), 44)
        self.assertTrue(Payment.objects.filter(application__property__name="Demo Ridge Apartments", status="completed").exists())
        self.assertTrue(Payment.objects.filter(application__property__name="Cedar Market Lofts", status="completed").exists())
        self.assertTrue(FinancialEntry.objects.filter(property_name="Demo Ridge Apartments").exists())
        self.assertTrue(FinancialEntry.objects.filter(property_name="Harbor View Senior Living").exists())
        self.assertEqual(RentalListing.objects.count(), 4)
        self.assertEqual(RentalListingChannel.objects.count(), 20)
        self.assertEqual(AccountingReceipt.objects.filter(status="approved").count(), 16)
        self.assertTrue(ResidentUtilitySetup.objects.exists())
        self.assertTrue(HousingApplication.objects.filter(background_check_required=True, screening_score__isnull=False).exists())
        self.assertTrue(PropertyOwnerIntake.objects.filter(lead_stage="demo_scheduled").exists())
        self.assertTrue(ResidentMessageReply.objects.filter(body__icontains="vendor update").exists())

        response = self.client.get(reverse("demo_entry"))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("superadmin_dashboard"))
        self.assertEqual(self.client.session.get("_auth_user_id"), str(User.objects.get(username="demo-admin").id))

    def test_demo_status_reports_running_demo_settings(self):
        response = self.client.get(reverse("demo_status"))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["demo_route_installed"])
        self.assertFalse(response.json()["demo_mode"])

    def test_commercial_custom_reports_use_scoped_property_data(self):
        owner = User.objects.create_user(
            username="commercial-report-owner",
            email="commercial-owner@example.com",
            password="StrongPass123!",
            role="property_owner",
        )
        property_obj = Property.objects.create(name="Commercial Report Property", owner_email=owner.email)
        hidden_property = Property.objects.create(name="Hidden Commercial Property", owner_email="hidden@example.com")
        PropertyRoomRent.objects.create(property=property_obj, room_unit_label="A", monthly_rent=Decimal("900.00"))
        PropertyRoomRent.objects.create(property=property_obj, room_unit_label="B", monthly_rent=Decimal("950.00"))
        tenant_user = User.objects.create_user(username="commercial-report-tenant", password="StrongPass123!", role="tenant")
        resident = HousingApplication.objects.create(
            property=property_obj,
            user=tenant_user,
            full_name="Commercial Report Resident",
            phone="555-0888",
            email="commercial-resident@example.com",
            age=44,
            space_label="A",
            monthly_rent=Decimal("900.00"),
            balance=Decimal("100.00"),
            utility_balance=Decimal("25.00"),
            deposit_required=Decimal("450.00"),
            deposit_paid=Decimal("300.00"),
            income_source="Employment",
            monthly_income=Decimal("3200.00"),
            housing_need="Current resident.",
        )
        Payment.objects.create(
            application=resident,
            payment_type="rent",
            amount=Decimal("900.00"),
            status="completed",
            service_month=date(2026, 5, 1),
        )
        upload = FinancialUpload.objects.create(
            property=property_obj,
            name="Commercial Summary",
            file=SimpleUploadedFile("summary.csv", b"category,amount\n", content_type="text/csv"),
        )
        for entry_type, category, amount in [
            ("income", "Rent", Decimal("1000.00")),
            ("operating_expense", "Power", Decimal("200.00")),
            ("operating_expense", "Insurance", Decimal("300.00")),
            ("debt_service", "Debt Service", Decimal("250.00")),
            ("capital_expense", "Windows", Decimal("500.00")),
        ]:
            FinancialEntry.objects.create(
                upload=upload,
                property_name=property_obj.name,
                sheet_name="Summary",
                row_number=1,
                entry_date=date(2026, 5, 1),
                year=2026,
                month=5,
                entry_type=entry_type,
                category=category,
                description=f"{category} line",
                amount=amount,
            )
        hidden_upload = FinancialUpload.objects.create(
            property=hidden_property,
            name="Hidden Summary",
            file=SimpleUploadedFile("hidden.csv", b"category,amount\n", content_type="text/csv"),
        )
        FinancialEntry.objects.create(
            upload=hidden_upload,
            property_name=hidden_property.name,
            sheet_name="Summary",
            row_number=1,
            entry_date=date(2026, 5, 1),
            year=2026,
            month=5,
            entry_type="operating_expense",
            category="Hidden Expense",
            description="Should not show",
            amount=Decimal("999.00"),
        )
        AccountingReceipt.objects.create(
            property=property_obj,
            vendor="Pacific Power",
            receipt_file=SimpleUploadedFile("receipt.txt", b"receipt", content_type="text/plain"),
            receipt_date=date(2026, 5, 2),
            amount=Decimal("200.00"),
            status="approved",
        )

        self.client.login(username="commercial-report-owner", password="StrongPass123!")

        valuation = self.client.get(reverse("custom_reports"), {"report_type": "valuation_estimate", "property_id": property_obj.id, "start_date": "2026-05-01"})
        utility = self.client.get(reverse("custom_reports"), {"report_type": "utility_cost_trend", "property_id": property_obj.id})
        vendor = self.client.get(reverse("custom_reports"), {"report_type": "vendor_expense", "property_id": property_obj.id})
        occupancy = self.client.get(reverse("custom_reports"), {"report_type": "occupancy_vacancy", "property_id": property_obj.id})
        delinquency = self.client.get(reverse("custom_reports"), {"report_type": "delinquency_report", "property_id": property_obj.id})
        capital = self.client.get(reverse("custom_reports"), {"report_type": "capital_improvement_log", "property_id": property_obj.id})
        insurance = self.client.get(reverse("custom_reports"), {"report_type": "insurance_compliance", "property_id": property_obj.id})

        self.assertContains(valuation, "Valuation Estimate Report")
        self.assertContains(valuation, "1 months annualized")
        self.assertContains(utility, "Power")
        self.assertContains(vendor, "Pacific Power")
        self.assertContains(occupancy, "Occupancy / Vacancy Report")
        self.assertContains(occupancy, "50.00%")
        self.assertContains(delinquency, "Commercial Report Resident")
        self.assertContains(capital, "Windows")
        self.assertContains(insurance, "Insurance / Compliance Report")
        self.assertNotContains(utility, "Hidden Expense")

    def test_t12_report_includes_uploaded_income_and_expenses(self):
        landlord = User.objects.create_user(
            username="t12-landlord",
            email="t12-landlord@example.com",
            password="StrongPass123!",
            role="landlord",
            is_staff=True,
        )
        property_obj = Property.objects.create(name="T12 Property", landlord_email=landlord.email)
        tenant_user = User.objects.create_user(username="t12-tenant", password="StrongPass123!", role="tenant")
        resident = HousingApplication.objects.create(
            property=property_obj,
            user=tenant_user,
            full_name="T12 Resident",
            phone="555-0701",
            email="t12-resident@example.com",
            age=47,
            monthly_rent=Decimal("700.00"),
            income_source="Employment",
            monthly_income=Decimal("3000.00"),
            housing_need="Current resident.",
        )
        upload = FinancialUpload.objects.create(
            property=property_obj,
            name="T12 Spreadsheet",
            file=SimpleUploadedFile("t12.csv", b"category,amount\n", content_type="text/csv"),
        )
        FinancialEntry.objects.create(
            upload=upload,
            property_name=property_obj.name,
            sheet_name="Summary",
            row_number=1,
            year=2026,
            month=6,
            entry_type="income",
            category="Rent",
            amount=Decimal("1200.00"),
        )
        FinancialEntry.objects.create(
            upload=upload,
            property_name=property_obj.name,
            sheet_name="Summary",
            row_number=2,
            year=2026,
            month=6,
            entry_type="operating_expense",
            category="Power",
            amount=Decimal("300.00"),
        )
        FinancialEntry.objects.create(
            upload=upload,
            property_name=property_obj.name,
            sheet_name="Summary",
            row_number=3,
            year=2026,
            month=6,
            entry_type="debt_service",
            category="Mortgage",
            amount=Decimal("400.00"),
        )
        Payment.objects.create(
            application=resident,
            payment_type="rent",
            amount=Decimal("700.00"),
            status="completed",
            service_month=date(2026, 6, 1),
        )
        Payment.objects.create(
            application=resident,
            payment_type="deposit",
            amount=Decimal("450.00"),
            status="completed",
            service_month=date(2026, 6, 1),
        )

        self.client.login(username="t12-landlord", password="StrongPass123!")
        response = self.client.get(f"{reverse('t12_report')}?year=2026")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Spreadsheet Income")
        self.assertContains(response, "Total Income")
        self.assertContains(response, "<td>$1200.00</td>", html=True)
        self.assertNotContains(response, "<td>$1900.00</td>", html=True)
        self.assertContains(response, "<td>$1200.00</td>", html=True)
        self.assertContains(response, "<td>$900.00</td>", html=True)
        self.assertContains(response, "<td>$500.00</td>", html=True)
        self.assertContains(response, "<td>$1200.00</td>", html=True)
        self.assertNotContains(response, "<td>$2350.00</td>", html=True)

        csv_response = self.client.get(f"{reverse('export_t12_csv')}?year=2026")
        csv_content = csv_response.content.decode()

        self.assertIn("June,Spreadsheet,0.00,1200.00,1200.00,300.00,400.00", csv_content)

    def test_t12_prefers_summary_income_over_portal_income_for_same_month(self):
        landlord = User.objects.create_user(
            username="t12-no-double-landlord",
            email="t12-no-double@example.com",
            password="StrongPass123!",
            role="landlord",
            is_staff=True,
        )
        property_obj = Property.objects.create(name="T12 No Double Property", landlord_email=landlord.email)
        tenant_user = User.objects.create_user(username="t12-no-double-tenant", password="StrongPass123!", role="tenant")
        resident = HousingApplication.objects.create(
            property=property_obj,
            user=tenant_user,
            full_name="No Double Resident",
            phone="555-0704",
            email="no-double@example.com",
            age=47,
            monthly_rent=Decimal("700.00"),
            income_source="Employment",
            monthly_income=Decimal("3000.00"),
            housing_need="Current resident.",
        )
        upload = FinancialUpload.objects.create(
            property=property_obj,
            name="No Double Summary",
            file=SimpleUploadedFile("no-double.csv", b"category,amount\n", content_type="text/csv"),
        )
        FinancialEntry.objects.create(
            upload=upload,
            property_name=property_obj.name,
            sheet_name="Summary",
            row_number=1,
            year=2026,
            month=5,
            entry_type="income",
            category="Rent",
            amount=Decimal("2000.00"),
        )
        FinancialEntry.objects.create(
            upload=upload,
            property_name=property_obj.name,
            sheet_name="Summary",
            row_number=2,
            year=2026,
            month=5,
            entry_type="operating_expense",
            category="Repairs",
            amount=Decimal("300.00"),
        )
        FinancialEntry.objects.create(
            upload=upload,
            property_name=property_obj.name,
            sheet_name="Summary",
            row_number=3,
            year=2026,
            month=5,
            entry_type="debt_service",
            category="Debt Service",
            amount=Decimal("500.00"),
        )
        Payment.objects.create(
            application=resident,
            payment_type="rent",
            amount=Decimal("700.00"),
            status="completed",
            service_month=date(2026, 5, 1),
        )

        months, totals = t12_report_rows(landlord, 2026)
        may_row = months[4]

        self.assertEqual(may_row["income_source"], "Spreadsheet")
        self.assertEqual(may_row["online_income"], Decimal("0.00"))
        self.assertEqual(may_row["spreadsheet_income"], Decimal("2000.00"))
        self.assertEqual(may_row["total_income"], Decimal("2000.00"))
        self.assertEqual(may_row["operating_expenses"], Decimal("300.00"))
        self.assertEqual(may_row["debt_service"], Decimal("500.00"))
        self.assertEqual(may_row["net_operating_income"], Decimal("1700.00"))
        self.assertEqual(may_row["cash_flow_after_debt"], Decimal("1200.00"))

    def test_t12_adds_receipts_created_after_summary_baseline(self):
        landlord = User.objects.create_user(
            username="t12-receipt-landlord",
            email="t12-receipt-landlord@example.com",
            password="StrongPass123!",
            role="landlord",
            is_staff=True,
        )
        property_obj = Property.objects.create(name="T12 Receipt Property", landlord_email=landlord.email)
        summary_upload = FinancialUpload.objects.create(
            property=property_obj,
            name="May Summary Snapshot",
            file=SimpleUploadedFile("summary.csv", b"Category,May\n", content_type="text/csv"),
        )
        FinancialEntry.objects.create(
            upload=summary_upload,
            property_name=property_obj.name,
            sheet_name="Summary",
            row_number=1,
            year=2026,
            month=5,
            entry_type="income",
            category="Rent",
            amount=Decimal("2000.00"),
        )
        FinancialEntry.objects.create(
            upload=summary_upload,
            property_name=property_obj.name,
            sheet_name="Summary",
            row_number=2,
            year=2026,
            month=5,
            entry_type="operating_expense",
            category="Repairs",
            amount=Decimal("300.00"),
        )
        receipt_category = ExpenseCategory.objects.create(name="Post Summary Repair", entry_type="operating_expense")
        receipt = AccountingReceipt.objects.create(
            property=property_obj,
            receipt_file="accounting_receipts/post-summary.pdf",
            vendor="Post Summary Vendor",
            receipt_date=date(2026, 5, 28),
            category=receipt_category,
            entry_type="operating_expense",
            description="Expense after summary snapshot",
            amount=Decimal("125.00"),
            payment_method="cash",
            status="approved",
        )
        receipt_upload = FinancialUpload.objects.create(
            property=property_obj,
            file="accounting_receipts/post-summary.pdf",
            name="Receipt - Post Summary Vendor",
            parsed_at=timezone.now(),
        )
        receipt.financial_upload = receipt_upload
        receipt.financial_entry = FinancialEntry.objects.create(
            upload=receipt_upload,
            property_name=property_obj.name,
            sheet_name="Receipt Upload",
            row_number=receipt.id,
            entry_date=receipt.receipt_date,
            month=5,
            year=2026,
            entry_type="operating_expense",
            category=receipt_category.name,
            description=receipt.description,
            amount=receipt.amount,
        )
        receipt.save(update_fields=["financial_upload", "financial_entry"])

        months, _totals = t12_report_rows(landlord, 2026)
        may_row = months[4]

        self.assertEqual(may_row["income_source"], "Spreadsheet")
        self.assertEqual(may_row["spreadsheet_income"], Decimal("2000.00"))
        self.assertEqual(may_row["operating_expenses"], Decimal("425.00"))
        self.assertEqual(may_row["net_operating_income"], Decimal("1575.00"))

    def test_t12_report_can_be_filtered_to_one_property(self):
        owner = User.objects.create_user(
            username="t12-filter-owner",
            email="t12-filter@example.com",
            password="StrongPass123!",
            role="property_owner",
            is_staff=True,
        )
        first_property = Property.objects.create(name="T12 First Property", owner_email=owner.email)
        second_property = Property.objects.create(name="T12 Second Property", owner_email=owner.email)
        first_upload = FinancialUpload.objects.create(
            property=first_property,
            name="First T12",
            file=SimpleUploadedFile("first.csv", b"Category,May\n", content_type="text/csv"),
        )
        second_upload = FinancialUpload.objects.create(
            property=second_property,
            name="Second T12",
            file=SimpleUploadedFile("second.csv", b"Category,May\n", content_type="text/csv"),
        )
        FinancialEntry.objects.create(
            upload=first_upload,
            property_name=first_property.name,
            sheet_name="Summary",
            row_number=1,
            year=2026,
            month=5,
            entry_type="operating_expense",
            category="Power",
            amount=Decimal("100.00"),
        )
        FinancialEntry.objects.create(
            upload=second_upload,
            property_name=second_property.name,
            sheet_name="Summary",
            row_number=1,
            year=2026,
            month=5,
            entry_type="operating_expense",
            category="Power",
            amount=Decimal("900.00"),
        )

        self.client.login(username="t12-filter-owner", password="StrongPass123!")
        response = self.client.get(f"{reverse('t12_report')}?year=2026&property_id={first_property.id}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["selected_property"], first_property)
        self.assertEqual(response.context["months"][4]["operating_expenses"], Decimal("100.00"))
        self.assertContains(response, "T12 First Property")
        self.assertNotContains(response, "<td>$900.00</td>", html=True)

    def test_t12_report_includes_entry_date_rows_and_property_name_scope(self):
        landlord = User.objects.create_user(
            username="t12-entry-date-landlord",
            email="t12-entry-date@example.com",
            password="StrongPass123!",
            role="landlord",
            is_staff=True,
        )
        property_obj = Property.objects.create(name="T12 Entry Date Property", landlord_email=landlord.email)
        other_property = Property.objects.create(name="Other T12 Property", landlord_email="other@example.com")
        upload = FinancialUpload.objects.create(
            property=None,
            name="Legacy Parsed Summary",
            file=SimpleUploadedFile("legacy-summary.csv", b"Category,May\n", content_type="text/csv"),
            parsed_at=timezone.now(),
        )
        other_upload = FinancialUpload.objects.create(
            property=other_property,
            name="Other Parsed Summary",
            file=SimpleUploadedFile("other-summary.csv", b"Category,May\n", content_type="text/csv"),
            parsed_at=timezone.now(),
        )
        FinancialEntry.objects.create(
            upload=upload,
            property_name=property_obj.name,
            sheet_name="Summary",
            row_number=2,
            entry_date=date(2026, 5, 1),
            entry_type="operating_expense",
            category="Power",
            description="Power - May summary",
            amount=Decimal("250.00"),
        )
        FinancialEntry.objects.create(
            upload=other_upload,
            property_name=other_property.name,
            sheet_name="Summary",
            row_number=2,
            entry_date=date(2026, 5, 1),
            entry_type="operating_expense",
            category="Other Power",
            description="Other property should not appear",
            amount=Decimal("999.00"),
        )

        self.client.login(username="t12-entry-date-landlord", password="StrongPass123!")
        response = self.client.get(f"{reverse('t12_report')}?year=2026")

        self.assertEqual(response.status_code, 200)
        may_row = response.context["months"][4]
        self.assertEqual(may_row["operating_expenses"], Decimal("250.00"))
        self.assertNotContains(response, "999.00")

    def test_accounting_receipt_upload_creates_category_and_review_record(self):
        landlord = User.objects.create_user(
            username="receipt-landlord",
            email="receipt-landlord@example.com",
            password="StrongPass123!",
            role="landlord",
            is_staff=True,
        )
        property_obj = Property.objects.create(name="Receipt Property", landlord_email=landlord.email)
        receipt_file = SimpleUploadedFile("receipt.pdf", b"%PDF-1.4 receipt", content_type="application/pdf")

        self.client.login(username="receipt-landlord", password="StrongPass123!")

        response = self.client.post(reverse("accounting_receipts"), {
            "property": property_obj.id,
            "receipt_file": receipt_file,
            "vendor": "Plumbing Vendor",
            "receipt_date": "2026-05-20",
            "entry_type": "operating_expense",
            "new_category": "Plumbing Repairs",
            "description": "Kitchen sink repair",
            "amount": "125.50",
            "payment_method": "check",
            "notes": "Uploaded from paper receipt.",
        })

        self.assertRedirects(response, reverse("accounting_receipts"))
        receipt = AccountingReceipt.objects.get(vendor="Plumbing Vendor")
        self.assertEqual(receipt.property, property_obj)
        self.assertEqual(receipt.status, "needs_review")
        self.assertEqual(receipt.category.name, "Plumbing Repairs")
        self.assertTrue(receipt.receipt_file.name)

    def test_accounting_receipt_upload_extracts_text_suggestions(self):
        landlord = User.objects.create_user(
            username="ocr-receipt-landlord",
            email="ocr-receipt-landlord@example.com",
            password="StrongPass123!",
            role="landlord",
            is_staff=True,
        )
        property_obj = Property.objects.create(name="OCR Receipt Property", landlord_email=landlord.email)
        receipt_file = SimpleUploadedFile(
            "lowes-receipt.txt",
            b"LOWES HOME IMPROVEMENT\nDate: 05/25/2026\nPaint and supplies\nTotal: $151.13\n",
            content_type="text/plain",
        )

        self.client.login(username="ocr-receipt-landlord", password="StrongPass123!")

        response = self.client.post(reverse("accounting_receipts"), {
            "property": property_obj.id,
            "receipt_file": receipt_file,
            "vendor": "",
            "receipt_date": "",
            "entry_type": "operating_expense",
            "new_category": "Maintenance Supplies",
            "description": "Room reset supplies",
            "amount": "",
            "payment_method": "other",
            "notes": "",
        })

        self.assertRedirects(response, reverse("accounting_receipts"))
        receipt = AccountingReceipt.objects.get(property=property_obj)
        self.assertEqual(receipt.ocr_status, "extracted")
        self.assertIn("LOWES HOME IMPROVEMENT", receipt.ocr_text)
        self.assertEqual(receipt.vendor, "LOWES HOME IMPROVEMENT")
        self.assertEqual(receipt.receipt_date, date(2026, 5, 25))
        self.assertEqual(receipt.amount, Decimal("151.13"))
        self.assertEqual(receipt.ocr_suggested_amount, Decimal("151.13"))

    def test_accounting_receipt_upload_flags_scanned_image_for_ocr_provider(self):
        landlord = User.objects.create_user(
            username="scan-receipt-landlord",
            email="scan-receipt-landlord@example.com",
            password="StrongPass123!",
            role="landlord",
            is_staff=True,
        )
        property_obj = Property.objects.create(name="Scanned Receipt Property", landlord_email=landlord.email)
        receipt_file = SimpleUploadedFile(
            "scanned-receipt.jpg",
            b"\xff\xd8\xff\xe0fake-image-bytes",
            content_type="image/jpeg",
        )

        self.client.login(username="scan-receipt-landlord", password="StrongPass123!")

        response = self.client.post(reverse("accounting_receipts"), {
            "property": property_obj.id,
            "receipt_file": receipt_file,
            "vendor": "Image Vendor",
            "receipt_date": "",
            "entry_type": "operating_expense",
            "new_category": "Image Category",
            "description": "Scanned receipt",
            "amount": "0.00",
            "payment_method": "other",
            "notes": "",
        })

        self.assertRedirects(response, reverse("accounting_receipts"))
        receipt = AccountingReceipt.objects.get(property=property_obj)
        self.assertEqual(receipt.ocr_status, "needs_ocr_provider")
        self.assertIn("OCR provider", receipt.ocr_error)

    @override_settings(RECEIPT_OCR_PROVIDER="ocr_space", OCR_SPACE_API_KEY="test-key")
    @patch("main.receipt_ocr.requests.post")
    def test_accounting_receipt_upload_uses_configured_ocr_provider(self, mock_post):
        class FakeOcrResponse:
            status_code = 200

            def json(self):
                return {
                    "IsErroredOnProcessing": False,
                    "ParsedResults": [
                        {
                            "ParsedText": "AVISTA UTILITIES\n06/01/2026\nPower service\nTotal: $736.40"
                        }
                    ],
                }

        mock_post.return_value = FakeOcrResponse()
        landlord = User.objects.create_user(
            username="provider-ocr-landlord",
            email="provider-ocr-landlord@example.com",
            password="StrongPass123!",
            role="landlord",
            is_staff=True,
        )
        property_obj = Property.objects.create(name="Provider OCR Property", landlord_email=landlord.email)
        receipt_file = SimpleUploadedFile(
            "avista-scan.jpg",
            b"\xff\xd8\xff\xe0fake-image-bytes",
            content_type="image/jpeg",
        )

        self.client.login(username="provider-ocr-landlord", password="StrongPass123!")

        response = self.client.post(reverse("accounting_receipts"), {
            "property": property_obj.id,
            "receipt_file": receipt_file,
            "vendor": "",
            "receipt_date": "",
            "entry_type": "operating_expense",
            "new_category": "Power",
            "description": "Power bill",
            "amount": "",
            "payment_method": "other",
            "notes": "",
        })

        self.assertRedirects(response, reverse("accounting_receipts"))
        receipt = AccountingReceipt.objects.get(property=property_obj)
        self.assertEqual(receipt.ocr_status, "extracted")
        self.assertEqual(receipt.vendor, "AVISTA UTILITIES")
        self.assertEqual(receipt.receipt_date, date(2026, 6, 1))
        self.assertEqual(receipt.amount, Decimal("736.40"))
        mock_post.assert_called_once()

    def test_accounting_receipt_approval_creates_financial_entry_and_scopes_property(self):
        landlord = User.objects.create_user(
            username="approve-receipt-landlord",
            email="approve-receipt-landlord@example.com",
            password="StrongPass123!",
            role="landlord",
            is_staff=True,
        )
        property_obj = Property.objects.create(name="Approval Property", landlord_email=landlord.email)
        other_property = Property.objects.create(name="Other Approval Property", landlord_email="other@example.com")
        category = ExpenseCategory.objects.create(name="Repairs", entry_type="operating_expense")
        receipt = AccountingReceipt.objects.create(
            property=property_obj,
            receipt_file="accounting_receipts/repair.pdf",
            vendor="Repair Vendor",
            receipt_date=timezone.datetime(2026, 5, 20).date(),
            category=category,
            entry_type="operating_expense",
            description="Door repair",
            amount=Decimal("225.00"),
            payment_method="cash",
        )
        other_receipt = AccountingReceipt.objects.create(
            property=other_property,
            receipt_file="accounting_receipts/other.pdf",
            vendor="Other Vendor",
            category=category,
            amount=Decimal("99.00"),
        )

        self.client.login(username="approve-receipt-landlord", password="StrongPass123!")

        blocked_response = self.client.post(reverse("approve_accounting_receipt", args=[other_receipt.id]))
        self.assertEqual(blocked_response.status_code, 404)

        response = self.client.post(reverse("approve_accounting_receipt", args=[receipt.id]))

        self.assertRedirects(response, reverse("accounting_receipts"))
        receipt.refresh_from_db()
        self.assertEqual(receipt.status, "approved")
        self.assertIsNotNone(receipt.financial_entry)
        self.assertEqual(receipt.financial_entry.property_name, property_obj.name)
        self.assertEqual(receipt.financial_entry.category, "Repairs")
        self.assertEqual(receipt.financial_entry.amount, Decimal("225.00"))

    def test_duplicate_receipt_approval_does_not_create_second_ledger_entry(self):
        landlord = User.objects.create_user(
            username="duplicate-receipt-landlord",
            email="duplicate-receipt-landlord@example.com",
            password="StrongPass123!",
            role="landlord",
            is_staff=True,
        )
        property_obj = Property.objects.create(name="Duplicate Receipt Property", landlord_email=landlord.email)
        category = ExpenseCategory.objects.create(name="Duplicate Repairs", entry_type="operating_expense")
        first_receipt = AccountingReceipt.objects.create(
            property=property_obj,
            receipt_file="accounting_receipts/repair-1.pdf",
            vendor="Repair Vendor",
            receipt_date=timezone.datetime(2026, 5, 20).date(),
            category=category,
            entry_type="operating_expense",
            description="Door repair",
            amount=Decimal("225.00"),
            payment_method="cash",
        )
        duplicate_receipt = AccountingReceipt.objects.create(
            property=property_obj,
            receipt_file="accounting_receipts/repair-2.pdf",
            vendor="Repair Vendor",
            receipt_date=timezone.datetime(2026, 5, 20).date(),
            category=category,
            entry_type="operating_expense",
            description="Door repair",
            amount=Decimal("225.00"),
            payment_method="cash",
        )

        self.client.login(username="duplicate-receipt-landlord", password="StrongPass123!")
        self.client.post(reverse("approve_accounting_receipt", args=[first_receipt.id]))
        response = self.client.post(reverse("approve_accounting_receipt", args=[duplicate_receipt.id]))

        self.assertRedirects(response, reverse("accounting_receipts"))
        duplicate_receipt.refresh_from_db()
        self.assertEqual(duplicate_receipt.status, "ignored")
        self.assertEqual(
            FinancialEntry.objects.filter(
                property_name=property_obj.name,
                category="Duplicate Repairs",
                description="Door repair",
                amount=Decimal("225.00"),
            ).count(),
            1,
        )

    def test_accounting_import_maps_csv_to_property_scoped_ledger_entries(self):
        landlord = User.objects.create_user(
            username="accounting-landlord",
            email="accounting-landlord@example.com",
            password="StrongPass123!",
            role="landlord",
            is_staff=True,
        )
        property_obj = Property.objects.create(name="Accounting Property", landlord_email=landlord.email)
        csv_file = SimpleUploadedFile(
            "expenses.csv",
            b"Date,Vendor,Amount,Category\n2026-05-01,Power Company,-125.50,Utilities\n2026-05-03,Roof Vendor,-900.00,Capital Roof\n",
            content_type="text/csv",
        )

        self.client.login(username="accounting-landlord", password="StrongPass123!")
        upload_response = self.client.post(reverse("financial_upload"), {
            "property": property_obj.id,
            "ledger_scope": "property",
            "name": "May Expenses",
            "file": csv_file,
            "notes": "Bank export",
        })

        upload = FinancialUpload.objects.get(name="May Expenses")
        self.assertRedirects(upload_response, reverse("parse_financial_upload", args=[upload.id]))

        response = self.client.post(reverse("parse_financial_upload", args=[upload.id]), {
            "date_column": "Date",
            "description_column": "Vendor",
            "amount_column": "Amount",
            "category_column": "Category",
            "entry_type_column": "",
            "property_column": "",
            "default_entry_type": "operating_expense",
            "default_category": "",
        })

        self.assertRedirects(response, reverse("financial_upload"))
        entries = FinancialEntry.objects.filter(upload=upload).order_by("row_number")
        self.assertEqual(entries.count(), 2)
        self.assertEqual(entries[0].property_name, property_obj.name)
        self.assertEqual(entries[0].entry_date.isoformat(), "2026-05-01")
        self.assertEqual(entries[0].amount, Decimal("125.50"))
        self.assertEqual(entries[0].category, "Utilities")
        self.assertEqual(entries[1].entry_type, "capital_expense")
        self.assertTrue(ExpenseCategory.objects.filter(name="Utilities").exists())

    def test_duplicate_financial_upload_does_not_create_second_ledger_entry(self):
        landlord = User.objects.create_user(
            username="duplicate-upload-landlord",
            email="duplicate-upload-landlord@example.com",
            password="StrongPass123!",
            role="landlord",
            is_staff=True,
        )
        property_obj = Property.objects.create(name="Duplicate Upload Property", landlord_email=landlord.email)

        self.client.login(username="duplicate-upload-landlord", password="StrongPass123!")
        for upload_name in ["May Expenses Original", "May Expenses Duplicate"]:
            csv_file = SimpleUploadedFile(
                f"{upload_name}.csv",
                b"Date,Vendor,Amount,Category\n2026-05-01,Power Company,-125.50,Utilities\n",
                content_type="text/csv",
            )
            self.client.post(reverse("financial_upload"), {
                "property": property_obj.id,
                "ledger_scope": "property",
                "name": upload_name,
                "file": csv_file,
                "notes": "Bank export",
            })
            upload = FinancialUpload.objects.get(name=upload_name)
            self.client.post(reverse("parse_financial_upload", args=[upload.id]), {
                "date_column": "Date",
                "description_column": "Vendor",
                "amount_column": "Amount",
                "category_column": "Category",
                "entry_type_column": "",
                "property_column": "",
                "default_entry_type": "operating_expense",
                "default_category": "",
            })

        self.assertEqual(
            FinancialEntry.objects.filter(
                property_name=property_obj.name,
                entry_date=timezone.datetime(2026, 5, 1).date(),
                category="Utilities",
                description="Power Company",
                amount=Decimal("125.50"),
            ).count(),
            1,
        )

    def test_accounting_import_can_split_rent_utilities_and_deposits(self):
        landlord = User.objects.create_user(
            username="split-ledger-landlord",
            email="split-ledger-landlord@example.com",
            password="StrongPass123!",
            role="landlord",
            is_staff=True,
        )
        property_obj = Property.objects.create(name="Split Ledger Property", landlord_email=landlord.email)
        csv_file = SimpleUploadedFile(
            "rent-roll.csv",
            b"Date,Resident,Rent,Utilities,Deposit\n2026-06-01,Felicia Valdez,500.00,75.00,150.00\n",
            content_type="text/csv",
        )

        self.client.login(username="split-ledger-landlord", password="StrongPass123!")
        self.client.post(reverse("financial_upload"), {
            "property": property_obj.id,
            "ledger_scope": "property",
            "name": "June Rent Roll",
            "file": csv_file,
            "notes": "Rent roll export",
        })

        upload = FinancialUpload.objects.get(name="June Rent Roll")
        response = self.client.post(reverse("parse_financial_upload", args=[upload.id]), {
            "date_column": "Date",
            "description_column": "Resident",
            "amount_column": "Rent",
            "utility_amount_column": "Utilities",
            "deposit_amount_column": "Deposit",
            "other_income_amount_column": "",
            "category_column": "",
            "entry_type_column": "",
            "property_column": "",
            "default_entry_type": "income",
            "default_category": "Rent Income",
        })

        self.assertRedirects(response, reverse("financial_upload"))
        entries = FinancialEntry.objects.filter(upload=upload).order_by("category")
        self.assertEqual(entries.count(), 3)
        self.assertEqual(sum((entry.amount for entry in entries), Decimal("0.00")), Decimal("725.00"))
        self.assertTrue(entries.filter(category="Utility Payment", amount=Decimal("75.00")).exists())
        self.assertTrue(entries.filter(category="Deposit Payment", amount=Decimal("150.00")).exists())

    def test_accounting_import_supports_monthly_summary_grid(self):
        landlord = User.objects.create_user(
            username="summary-grid-landlord",
            email="summary-grid-landlord@example.com",
            password="StrongPass123!",
            role="landlord",
            is_staff=True,
        )
        property_obj = Property.objects.create(name="Summary Grid Property", landlord_email=landlord.email)
        csv_file = SimpleUploadedFile(
            "summary.csv",
            b"Category,January,February,March,Q1 Total\nRepairs,100.00,200.00,300.00,600.00\nUtilities,50.00,60.00,70.00,180.00\n",
            content_type="text/csv",
        )

        self.client.login(username="summary-grid-landlord", password="StrongPass123!")
        self.client.post(reverse("financial_upload"), {
            "property": property_obj.id,
            "ledger_scope": "property",
            "name": "Q1 Summary",
            "file": csv_file,
            "notes": "Monthly summary sheet",
        })

        upload = FinancialUpload.objects.get(name="Q1 Summary")
        response = self.client.post(reverse("parse_financial_upload", args=[upload.id]), {
            "import_mode": "summary_grid",
            "sheet_name": "CSV",
            "summary_category_column": "Category",
            "summary_year": "2026",
            "summary_entry_type": "operating_expense",
            "summary_month_columns": ["January", "February", "March"],
        })

        self.assertRedirects(response, reverse("financial_upload"))
        entries = FinancialEntry.objects.filter(upload=upload).order_by("category", "month")
        self.assertEqual(entries.count(), 6)
        self.assertTrue(entries.filter(category="Repairs", month=1, year=2026, amount=Decimal("100.00")).exists())
        self.assertTrue(entries.filter(category="Utilities", month=3, year=2026, amount=Decimal("70.00")).exists())
        self.assertFalse(entries.filter(description__icontains="Q1 Total").exists())

    def test_summary_grid_skips_total_columns_and_utility_parent_rows(self):
        landlord = User.objects.create_user(
            username="summary-utility-parent-landlord",
            email="summary-utility-parent@example.com",
            password="StrongPass123!",
            role="landlord",
            is_staff=True,
        )
        property_obj = Property.objects.create(name="Summary Utility Property", landlord_email=landlord.email)
        csv_file = SimpleUploadedFile(
            "summary-utilities.csv",
            (
                b"Category,May,May Total,June\n"
                b"Utilities,500.00,500.00,550.00\n"
                b"Power,200.00,200.00,220.00\n"
                b"Gas,100.00,100.00,110.00\n"
                b"Water,150.00,150.00,165.00\n"
                b"Trash,50.00,50.00,55.00\n"
                b"Total Expenses,500.00,500.00,550.00\n"
            ),
            content_type="text/csv",
        )

        self.client.login(username="summary-utility-parent-landlord", password="StrongPass123!")
        self.client.post(reverse("financial_upload"), {
            "property": property_obj.id,
            "ledger_scope": "property",
            "name": "Utility Summary",
            "file": csv_file,
            "notes": "Monthly summary sheet",
        })

        upload = FinancialUpload.objects.get(name="Utility Summary")
        response = self.client.post(reverse("parse_financial_upload", args=[upload.id]), {
            "import_mode": "summary_grid",
            "sheet_name": "CSV",
            "summary_category_column": "Category",
            "summary_year": "2026",
            "summary_entry_type": "operating_expense",
            "summary_month_columns": ["May", "May Total", "June"],
        })

        self.assertRedirects(response, reverse("financial_upload"))
        entries = FinancialEntry.objects.filter(upload=upload)
        self.assertEqual(entries.count(), 8)
        self.assertFalse(entries.filter(category="Utilities").exists())
        self.assertFalse(entries.filter(category="Total Expenses").exists())
        self.assertFalse(entries.filter(description__icontains="May Total").exists())
        self.assertEqual(
            entries.filter(month=5).aggregate(total=Sum("amount"))["total"],
            Decimal("500.00"),
        )
        self.assertEqual(
            entries.filter(month=6).aggregate(total=Sum("amount"))["total"],
            Decimal("550.00"),
        )

    def test_summary_grid_classifies_rent_rows_as_income(self):
        landlord = User.objects.create_user(
            username="summary-rent-income-landlord",
            email="summary-rent-income@example.com",
            password="StrongPass123!",
            role="landlord",
            is_staff=True,
        )
        property_obj = Property.objects.create(name="Summary Rent Property", landlord_email=landlord.email)
        csv_file = SimpleUploadedFile(
            "summary-rent.csv",
            b"Category,May,June\nRent,1200.00,1300.00\nPower,100.00,120.00\n",
            content_type="text/csv",
        )

        self.client.login(username="summary-rent-income-landlord", password="StrongPass123!")
        self.client.post(reverse("financial_upload"), {
            "property": property_obj.id,
            "ledger_scope": "property",
            "name": "Rent Summary",
            "file": csv_file,
            "notes": "Monthly summary sheet",
        })

        upload = FinancialUpload.objects.get(name="Rent Summary")
        response = self.client.post(reverse("parse_financial_upload", args=[upload.id]), {
            "import_mode": "summary_grid",
            "sheet_name": "CSV",
            "summary_category_column": "Category",
            "summary_year": "2026",
            "summary_entry_type": "operating_expense",
            "summary_month_columns": ["May", "June"],
        })

        self.assertRedirects(response, reverse("financial_upload"))
        self.assertTrue(entries := FinancialEntry.objects.filter(upload=upload, category="Rent"))
        self.assertEqual(set(entries.values_list("entry_type", flat=True)), {"income"})
        self.assertTrue(FinancialEntry.objects.filter(upload=upload, category="Power", entry_type="operating_expense").exists())

    def test_summary_grid_skips_noi_and_cash_flow_calculated_rows(self):
        landlord = User.objects.create_user(
            username="summary-noi-landlord",
            email="summary-noi@example.com",
            password="StrongPass123!",
            role="landlord",
            is_staff=True,
        )
        property_obj = Property.objects.create(name="Summary NOI Property", landlord_email=landlord.email)
        csv_file = SimpleUploadedFile(
            "summary-noi.csv",
            b"Category,May,June\nRent,1200.00,1300.00\nRepairs,100.00,120.00\nNOI,1100.00,1180.00\nCash Flow,900.00,980.00\n",
            content_type="text/csv",
        )

        self.client.login(username="summary-noi-landlord", password="StrongPass123!")
        self.client.post(reverse("financial_upload"), {
            "property": property_obj.id,
            "ledger_scope": "property",
            "name": "NOI Summary",
            "file": csv_file,
            "notes": "Monthly summary sheet",
        })

        upload = FinancialUpload.objects.get(name="NOI Summary")
        response = self.client.post(reverse("parse_financial_upload", args=[upload.id]), {
            "import_mode": "summary_grid",
            "sheet_name": "CSV",
            "summary_category_column": "Category",
            "summary_year": "2026",
            "summary_entry_type": "operating_expense",
            "summary_month_columns": ["May", "June"],
        })

        self.assertRedirects(response, reverse("financial_upload"))
        entries = FinancialEntry.objects.filter(upload=upload)
        self.assertFalse(entries.filter(category__iexact="NOI").exists())
        self.assertFalse(entries.filter(category__iexact="Cash Flow").exists())
        self.assertTrue(entries.filter(category="Rent", entry_type="income").exists())
        self.assertTrue(entries.filter(category="Repairs", entry_type="operating_expense").exists())

    def test_summary_grid_imports_total_operating_expenses_when_no_detail_rows(self):
        landlord = User.objects.create_user(
            username="summary-total-expense-landlord",
            email="summary-total-expense@example.com",
            password="StrongPass123!",
            role="landlord",
            is_staff=True,
        )
        property_obj = Property.objects.create(name="Summary Total Expense Property", landlord_email=landlord.email)
        csv_file = SimpleUploadedFile(
            "summary-total-expense.csv",
            (
                b"OVERHEAD TITLE,January,February,March,Q1 2026,April,May\n"
                b"Rent,2000.00,2100.00,2200.00,6300.00,2300.00,2400.00\n"
                b"Other Income,100.00,110.00,120.00,330.00,130.00,140.00\n"
                b"Total Operating Expenses,700.00,710.00,720.00,2130.00,730.00,740.00\n"
                b"Debt Service,500.00,500.00,500.00,1500.00,500.00,500.00\n"
                b"Resident Deposit,450.00,0.00,0.00,450.00,0.00,450.00\n"
                b"NOI,1300.00,1390.00,1480.00,4170.00,1570.00,1660.00\n"
                b"Total Net After Debt Service,800.00,890.00,980.00,2670.00,1070.00,1160.00\n"
                b"Cash Flow,800.00,890.00,980.00,2670.00,1070.00,1160.00\n"
            ),
            content_type="text/csv",
        )

        self.client.login(username="summary-total-expense-landlord", password="StrongPass123!")
        self.client.post(reverse("financial_upload"), {
            "property": property_obj.id,
            "ledger_scope": "property",
            "name": "Summary Total Expense",
            "file": csv_file,
            "notes": "Monthly summary sheet",
        })

        upload = FinancialUpload.objects.get(name="Summary Total Expense")
        response = self.client.post(reverse("parse_financial_upload", args=[upload.id]), {
            "import_mode": "summary_grid",
            "sheet_name": "CSV",
            "summary_category_column": "OVERHEAD TITLE",
            "summary_year": "2026",
            "summary_entry_type": "operating_expense",
            "summary_month_columns": ["January", "February", "March", "Q1 2026", "April", "May"],
        })

        self.assertRedirects(response, reverse("financial_upload"))
        entries = FinancialEntry.objects.filter(upload=upload)
        self.assertEqual(entries.count(), 22)
        self.assertTrue(entries.filter(category="Total Operating Expenses", month=5, entry_type="operating_expense", amount=Decimal("740.00")).exists())
        self.assertTrue(entries.filter(category="Debt Service", month=5, entry_type="debt_service", amount=Decimal("500.00")).exists())
        self.assertTrue(entries.filter(category="Other Income", month=5, entry_type="income", amount=Decimal("140.00")).exists())
        self.assertTrue(entries.filter(category="Resident Deposit", month=5, entry_type="income", amount=Decimal("450.00")).exists())
        self.assertFalse(entries.filter(description__icontains="Q1 2026").exists())
        self.assertFalse(entries.filter(category="NOI").exists())
        self.assertFalse(entries.filter(category="Cash Flow").exists())
        self.assertFalse(entries.filter(category="Total Net After Debt Service").exists())

        months, totals = t12_report_rows(landlord, 2026)
        may_row = months[4]
        self.assertEqual(may_row["spreadsheet_income"], Decimal("2540.00"))
        self.assertEqual(may_row["operating_expenses"], Decimal("740.00"))
        self.assertEqual(may_row["debt_service"], Decimal("500.00"))
        self.assertEqual(may_row["net_operating_income"], Decimal("1800.00"))
        self.assertEqual(may_row["cash_flow_after_debt"], Decimal("1300.00"))

    def test_summary_import_mapper_preselects_month_columns(self):
        landlord = User.objects.create_user(
            username="summary-month-picker-landlord",
            email="summary-month-picker@example.com",
            password="StrongPass123!",
            role="landlord",
            is_staff=True,
        )
        property_obj = Property.objects.create(name="Summary Month Picker Property", landlord_email=landlord.email)
        csv_file = SimpleUploadedFile(
            "summary-picker.csv",
            b"OVERHEAD TITLE,JANUARY,FEBRUARY,MARCH,Q1 2026,APRIL,MAY\nRent,2000.00,2100.00,2200.00,6300.00,2300.00,2400.00\n",
            content_type="text/csv",
        )

        self.client.login(username="summary-month-picker-landlord", password="StrongPass123!")
        self.client.post(reverse("financial_upload"), {
            "property": property_obj.id,
            "ledger_scope": "property",
            "name": "Summary Picker",
            "file": csv_file,
            "notes": "Monthly summary sheet",
        })

        upload = FinancialUpload.objects.get(name="Summary Picker")
        response = self.client.get(reverse("parse_financial_upload", args=[upload.id]))

        self.assertEqual(response.status_code, 200)
        month_options = response.context["summary_month_headers"]
        selected = {option["name"]: option["is_month"] for option in month_options}
        self.assertTrue(selected["JANUARY"])
        self.assertTrue(selected["MAY"])
        self.assertFalse(selected["Q1 2026"])

    def test_import_summary_grid_command_creates_t12_entries(self):
        landlord = User.objects.create_user(
            username="summary-command-landlord",
            email="summary-command@example.com",
            password="StrongPass123!",
            role="landlord",
            is_staff=True,
        )
        property_obj = Property.objects.create(name="Summary Command Property", landlord_email=landlord.email)
        csv_file = SimpleUploadedFile(
            "summary-command.csv",
            (
                b"OVERHEAD TITLE,JANUARY,FEBRUARY,MARCH,Q1 2026,APRIL,MAY\n"
                b"Rent,2000.00,2100.00,2200.00,6300.00,2300.00,2400.00\n"
                b"TOTAL OPERATING EXPENSES,700.00,710.00,720.00,2130.00,730.00,740.00\n"
                b"Debt Service,500.00,500.00,500.00,1500.00,500.00,500.00\n"
                b"Resident Deposit,450.00,0.00,0.00,450.00,0.00,450.00\n"
                b"Utility Account,100.00,110.00,120.00,330.00,130.00,140.00\n"
                b"Insurance,0.00,0.00,880.47,1760.94,880.47,880.47\n"
                b"Insurance,0.00,0.00,880.47,1760.94,880.47,880.47\n"
                b"NOI,1300.00,1390.00,1480.00,4170.00,1570.00,1660.00\n"
            ),
            content_type="text/csv",
        )
        upload = FinancialUpload.objects.create(
            property=property_obj,
            ledger_scope="property",
            name="Command Summary",
            file=csv_file,
        )

        preview = StringIO()
        call_command(
            "import_summary_grid",
            "--property-name",
            property_obj.name,
            "--year",
            "2026",
            "--upload-id",
            str(upload.id),
            stdout=preview,
        )
        self.assertEqual(FinancialEntry.objects.filter(upload=upload).count(), 0)
        self.assertIn("Duplicate entries skipped: 3", preview.getvalue())
        self.assertIn("Entries selected: 13", preview.getvalue())

        output = StringIO()
        call_command(
            "import_summary_grid",
            "--property-name",
            property_obj.name,
            "--year",
            "2026",
            "--upload-id",
            str(upload.id),
            "--confirm",
            stdout=output,
        )

        entries = FinancialEntry.objects.filter(upload=upload)
        self.assertEqual(entries.count(), 13)
        self.assertFalse(entries.filter(category="Resident Deposit").exists())
        self.assertFalse(entries.filter(category="Utility Account").exists())
        self.assertEqual(entries.filter(category="Insurance").count(), 3)
        months, _totals = t12_report_rows(landlord, 2026)
        may_row = months[4]
        self.assertEqual(may_row["spreadsheet_income"], Decimal("2400.00"))
        self.assertEqual(may_row["operating_expenses"], Decimal("880.47"))
        self.assertEqual(may_row["debt_service"], Decimal("500.00"))
        self.assertEqual(may_row["net_operating_income"], Decimal("1519.53"))
        self.assertEqual(may_row["cash_flow_after_debt"], Decimal("1019.53"))

    def test_import_monthly_rent_roll_command_imports_supporting_detail_without_t12_entries(self):
        landlord = User.objects.create_user(
            username="rent-roll-import-landlord",
            email="rent-roll-import@example.com",
            password="StrongPass123!",
            role="landlord",
            is_staff=True,
        )
        property_obj = Property.objects.create(name="Rent Roll Import Property", landlord_email=landlord.email)
        csv_file = SimpleUploadedFile(
            "jan-rent-roll.csv",
            (
                b"Painted Lady January Rent Roll,,,,,,,,\n"
                b",,,,,,,,\n"
                b"Room #,Tenant Name,Lease Start,Monthly Rent,Rent Paid,over/under,Deposit,new deposit,Shared Utilities\n"
                b"A,Office,,,,,,,\n"
                b"B,Grady Bradley,7/13/2014,$506.00,$506.00,$0.00,$450,,$58.00\n"
                b"C,Steven Bruno,2/26/2021,$610.00,$610.00,$0.00,$450,,$58.00\n"
                b"Q,VACANT,,,,,,,\n"
            ),
            content_type="text/csv",
        )
        upload = FinancialUpload.objects.create(
            property=property_obj,
            ledger_scope="property",
            name="Jan 26 Financial Upload",
            file=csv_file,
        )
        FinancialEntry.objects.create(
            upload=upload,
            ledger_scope="property",
            property_name=property_obj.name,
            sheet_name="CSV",
            row_number=2,
            entry_type="income",
            category="Rent",
            amount=Decimal("1116.00"),
        )

        preview = StringIO()
        call_command(
            "import_monthly_rent_roll",
            "--property-name",
            property_obj.name,
            "--upload-id",
            str(upload.id),
            "--month",
            "2026-01",
            stdout=preview,
        )
        self.assertIn("Resident rows selected: 2", preview.getvalue())
        self.assertEqual(Payment.objects.filter(application__property=property_obj).count(), 0)
        self.assertEqual(upload.entries.count(), 1)

        output = StringIO()
        call_command(
            "import_monthly_rent_roll",
            "--property-name",
            property_obj.name,
            "--upload-id",
            str(upload.id),
            "--month",
            "2026-01",
            "--confirm",
            stdout=output,
        )

        self.assertEqual(upload.entries.count(), 0)
        self.assertEqual(PropertyRoomRent.objects.filter(property=property_obj).count(), 2)
        self.assertEqual(CurrentResidentRosterEntry.objects.filter(property=property_obj).count(), 2)
        self.assertEqual(HousingApplication.objects.filter(property=property_obj, user__isnull=True).count(), 2)
        self.assertEqual(Payment.objects.filter(application__property=property_obj, service_month=date(2026, 1, 1), status="completed").count(), 4)

        rows = rent_roll_rows_for_properties(landlord, date(2026, 1, 1), Property.objects.filter(id=property_obj.id))
        grady_row = next(row for row in rows if row["room"] == "B")
        self.assertEqual(grady_row["resident"], "Grady Bradley")
        self.assertEqual(grady_row["monthly_rent"], Decimal("506.00"))
        self.assertEqual(grady_row["rent_paid"], Decimal("506.00"))
        self.assertEqual(grady_row["utility_paid"], Decimal("58.00"))
        self.assertEqual(grady_row["rent_balance"], Decimal("0.00"))

    def test_accounting_import_blocks_other_landlord_property(self):
        landlord = User.objects.create_user(
            username="blocked-accounting-landlord",
            email="blocked-accounting-landlord@example.com",
            password="StrongPass123!",
            role="landlord",
            is_staff=True,
        )
        other_property = Property.objects.create(name="Other Accounting Property", landlord_email="other@example.com")
        csv_file = SimpleUploadedFile(
            "blocked.csv",
            b"Date,Vendor,Amount\n2026-05-01,Vendor,-10.00\n",
            content_type="text/csv",
        )

        self.client.login(username="blocked-accounting-landlord", password="StrongPass123!")
        response = self.client.post(reverse("financial_upload"), {
            "property": other_property.id,
            "name": "Blocked Upload",
            "file": csv_file,
            "notes": "",
        })

        self.assertEqual(response.status_code, 200)
        self.assertFalse(FinancialUpload.objects.filter(name="Blocked Upload").exists())

    def test_cleanup_financial_upload_command_previews_then_deletes_selected_upload(self):
        property_obj = Property.objects.create(name="Financial Cleanup Property")
        upload = FinancialUpload.objects.create(
            property=property_obj,
            name="Partial Workbook Import",
            file="financial_uploads/partial.xlsx",
            parsed_at=timezone.now(),
        )
        FinancialEntry.objects.create(
            upload=upload,
            property_name=property_obj.name,
            sheet_name="Wrong Sheet",
            row_number=1,
            entry_type="income",
            category="Rent",
            description="Partial duplicate",
            amount=Decimal("100.00"),
        )

        preview = StringIO()
        call_command("cleanup_financial_upload", "--upload-id", str(upload.id), stdout=preview)

        self.assertIn("Dry run only", preview.getvalue())
        self.assertTrue(FinancialUpload.objects.filter(id=upload.id).exists())
        self.assertEqual(FinancialEntry.objects.filter(upload=upload).count(), 1)

        output = StringIO()
        call_command("cleanup_financial_upload", "--upload-id", str(upload.id), "--confirm", stdout=output)

        self.assertIn("Uploads deleted: 1", output.getvalue())
        self.assertFalse(FinancialUpload.objects.filter(id=upload.id).exists())
        self.assertEqual(FinancialEntry.objects.filter(upload=upload).count(), 0)

    def test_landlord_can_send_setup_invite_for_saved_current_resident_intake(self):
        landlord = User.objects.create_user(
            username="resident-intake-landlord",
            email="resident-intake-landlord@example.com",
            password="StrongPass123!",
            role="landlord",
            is_staff=True,
        )
        property_obj = Property.objects.create(name="Intake Property", landlord_email=landlord.email)
        CurrentResidentRosterEntry.objects.create(
            property=property_obj,
            first_name="Saved",
            last_name="Resident",
            email="saved-resident@example.com",
            room_unit_label="Unit 4",
        )
        intake = ExistingResidentIntake.objects.create(
            property=property_obj,
            first_name="Saved",
            last_name="Resident",
            email="saved-resident@example.com",
            phone="555-0200",
            room_unit_label="Unit 4",
        )

        self.client.login(username="resident-intake-landlord", password="StrongPass123!")

        response = self.client.post(reverse("landlord_send_existing_resident_invite", args=[intake.id]))

        self.assertRedirects(response, reverse("landlord_attention"))
        application = HousingApplication.objects.get(email="saved-resident@example.com")
        self.assertEqual(application.property, property_obj)
        self.assertEqual(application.space_label, "Unit 4")
        self.assertIn(application.user.invite_code, mail.outbox[0].body)

    def test_current_resident_setup_uses_room_letter_rent(self):
        property_obj = Property.objects.create(name="Room Letter Intake Property", rent_amount=Decimal("400.00"))
        PropertyRoomRent.objects.create(
            property=property_obj,
            room_unit_label="B",
            monthly_rent=Decimal("575.00"),
            rent_due_day=4,
            utility_monthly=Decimal("65.00"),
            deposit_required=Decimal("450.00"),
            deposit_paid=Decimal("95.00"),
        )
        intake = ExistingResidentIntake.objects.create(
            property=property_obj,
            first_name="Grady",
            last_name="Brady",
            email="grady-room-rent@example.com",
            phone="555-0400",
            room_unit_label="B",
        )

        application = ensure_existing_resident_portal_application(intake)

        self.assertEqual(application.monthly_rent, Decimal("575.00"))
        self.assertEqual(application.balance, Decimal("575.00"))
        self.assertEqual(application.rent_due_day, 4)
        self.assertEqual(application.utility_monthly, Decimal("65.00"))
        self.assertEqual(application.utility_balance, Decimal("65.00"))
        self.assertEqual(application.deposit_required, Decimal("450.00"))
        self.assertEqual(application.deposit_paid, Decimal("95.00"))
        self.assertEqual(
            set(application.signed_documents.values_list("document_type", flat=True)),
            {"lease", "emergency_contact", "painted_lady_acknowledgment"},
        )

    def test_manual_current_resident_invite_requires_roster_match(self):
        landlord = User.objects.create_user(
            username="blocked-current-resident-invite",
            email="blocked-current-resident-invite@example.com",
            password="StrongPass123!",
            role="landlord",
            is_staff=True,
        )
        property_obj = Property.objects.create(name="Blocked Intake Property", landlord_email=landlord.email)
        CurrentResidentRosterEntry.objects.create(
            property=property_obj,
            first_name="Approved",
            last_name="Resident",
            email="approved@example.com",
            room_unit_label="A",
        )
        intake = ExistingResidentIntake.objects.create(
            property=property_obj,
            first_name="Unknown",
            last_name="Applicant",
            email="unknown-current@example.com",
            phone="555-0401",
            room_unit_label="Z",
        )

        self.client.login(username="blocked-current-resident-invite", password="StrongPass123!")
        response = self.client.post(reverse("landlord_send_existing_resident_invite", args=[intake.id]))

        self.assertRedirects(response, reverse("landlord_attention"))
        self.assertFalse(HousingApplication.objects.filter(email="unknown-current@example.com").exists())
        self.assertEqual(len(mail.outbox), 0)

    def test_staff_can_override_roster_match_for_current_resident_invite(self):
        landlord = User.objects.create_user(
            username="override-current-resident-invite",
            email="override-current-resident-invite@example.com",
            password="StrongPass123!",
            role="landlord",
            is_staff=True,
        )
        property_obj = Property.objects.create(name="Override Intake Property", landlord_email=landlord.email)
        CurrentResidentRosterEntry.objects.create(
            property=property_obj,
            first_name="Approved",
            last_name="Resident",
            email="approved@example.com",
            room_unit_label="A",
        )
        intake = ExistingResidentIntake.objects.create(
            property=property_obj,
            first_name="Hero",
            last_name="Lowe",
            email="hero-lowe@example.com",
            phone="555-0402",
            room_unit_label="N",
        )

        self.client.login(username="override-current-resident-invite", password="StrongPass123!")
        response = self.client.post(reverse("landlord_send_existing_resident_invite", args=[intake.id]), {
            "allow_roster_override": "on",
        })

        self.assertRedirects(response, reverse("landlord_attention"))
        application = HousingApplication.objects.get(email="hero-lowe@example.com")
        self.assertEqual(application.full_name, "Hero Lowe")
        self.assertEqual(application.space_label, "N")
        self.assertIn(application.user.invite_code, mail.outbox[0].body)

    def test_staff_can_delete_invalid_current_resident_setup_attempt(self):
        landlord = User.objects.create_user(
            username="delete-current-resident-intake",
            email="delete-current-resident-intake@example.com",
            password="StrongPass123!",
            role="landlord",
            is_staff=True,
        )
        property_obj = Property.objects.create(name="Delete Intake Property", landlord_email=landlord.email)
        intake = ExistingResidentIntake.objects.create(
            property=property_obj,
            first_name="Invalid",
            last_name="Attempt",
            email="invalid-current@example.com",
            phone="555-0403",
            room_unit_label="Z",
        )

        self.client.login(username="delete-current-resident-intake", password="StrongPass123!")
        response = self.client.post(reverse("delete_existing_resident_intake", args=[intake.id]))

        self.assertRedirects(response, reverse("landlord_attention"))
        self.assertFalse(ExistingResidentIntake.objects.filter(id=intake.id).exists())

    def test_staff_cannot_delete_current_resident_setup_with_resident_file(self):
        landlord = User.objects.create_user(
            username="keep-linked-current-resident-intake",
            email="keep-linked-current-resident-intake@example.com",
            password="StrongPass123!",
            role="landlord",
            is_staff=True,
        )
        resident_user = User.objects.create_user(
            username="keep-linked-resident",
            email="linked-current@example.com",
            password="StrongPass123!",
            role="tenant",
        )
        property_obj = Property.objects.create(name="Keep Intake Property", landlord_email=landlord.email)
        intake = ExistingResidentIntake.objects.create(
            property=property_obj,
            first_name="Linked",
            last_name="Resident",
            email="linked-current@example.com",
            phone="555-0404",
            room_unit_label="A",
        )
        application = HousingApplication.objects.create(
            property=property_obj,
            user=resident_user,
            full_name="Linked Resident",
            phone="555-0404",
            email="linked-current@example.com",
            age=50,
            income_source="Existing resident intake",
            monthly_income=Decimal("0.00"),
            housing_need="Existing resident.",
        )
        intake.application = application
        intake.save(update_fields=["application"])

        self.client.login(username="keep-linked-current-resident-intake", password="StrongPass123!")
        response = self.client.post(reverse("delete_existing_resident_intake", args=[intake.id]))

        self.assertRedirects(response, reverse("landlord_existing_resident_intake_detail", args=[intake.id]))
        self.assertTrue(ExistingResidentIntake.objects.filter(id=intake.id).exists())

    def test_staff_can_delete_bad_email_setup_with_unused_code(self):
        landlord = User.objects.create_user(
            username="delete-unused-code-current-resident",
            email="delete-unused-code-current-resident@example.com",
            password="StrongPass123!",
            role="landlord",
            is_staff=True,
        )
        temp_user = User.objects.create_user(
            username="bad-email-temp",
            email="bad-email@example.com",
            password=None,
            role="tenant",
        )
        temp_user.refresh_invite_code()
        property_obj = Property.objects.create(name="Bad Email Intake Property", landlord_email=landlord.email)
        intake = ExistingResidentIntake.objects.create(
            property=property_obj,
            first_name="Bad",
            last_name="Email",
            email="bad-email@example.com",
            phone="555-0405",
            room_unit_label="L",
        )
        application = HousingApplication.objects.create(
            property=property_obj,
            user=temp_user,
            full_name="Bad Email",
            phone="555-0405",
            email="bad-email@example.com",
            age=50,
            income_source="Existing resident intake",
            monthly_income=Decimal("0.00"),
            housing_need="Existing resident.",
        )
        intake.application = application
        intake.save(update_fields=["application"])

        self.client.login(username="delete-unused-code-current-resident", password="StrongPass123!")
        response = self.client.post(reverse("delete_existing_resident_intake", args=[intake.id]))

        self.assertRedirects(response, reverse("landlord_attention"))
        self.assertFalse(ExistingResidentIntake.objects.filter(id=intake.id).exists())
        self.assertFalse(HousingApplication.objects.filter(id=application.id).exists())
        self.assertFalse(User.objects.filter(id=temp_user.id).exists())

    def test_duplicate_setup_attempt_actions_stay_on_selected_intake(self):
        landlord = User.objects.create_user(
            username="duplicate-current-resident-intake",
            email="duplicate-current-resident-intake@example.com",
            password="StrongPass123!",
            role="landlord",
            is_staff=True,
        )
        property_obj = Property.objects.create(name="Duplicate Intake Property", landlord_email=landlord.email)
        first_intake = ExistingResidentIntake.objects.create(
            property=property_obj,
            first_name="Mike",
            last_name="Dudy",
            email="wrong@example.com",
            phone="555-0406",
            room_unit_label="L",
        )
        second_intake = ExistingResidentIntake.objects.create(
            property=property_obj,
            first_name="Michael",
            last_name="Dudley",
            email="right@example.com",
            phone="555-0406",
            room_unit_label="L",
        )

        first_application = ensure_existing_resident_portal_application(first_intake)
        second_application = ensure_existing_resident_portal_application(second_intake)

        self.assertNotEqual(first_application.id, second_application.id)
        self.assertEqual(first_intake.application_id, first_application.id)
        self.assertEqual(second_intake.application_id, second_application.id)

        self.client.login(username="duplicate-current-resident-intake", password="StrongPass123!")
        response = self.client.post(reverse("delete_existing_resident_intake", args=[first_intake.id]))

        self.assertRedirects(response, reverse("landlord_attention"))
        self.assertFalse(ExistingResidentIntake.objects.filter(id=first_intake.id).exists())
        self.assertFalse(HousingApplication.objects.filter(id=first_application.id).exists())
        self.assertTrue(ExistingResidentIntake.objects.filter(id=second_intake.id).exists())
        self.assertTrue(HousingApplication.objects.filter(id=second_application.id).exists())

    def test_landlord_can_upload_current_resident_roster(self):
        landlord = User.objects.create_user(
            username="roster-landlord",
            email="roster-landlord@example.com",
            password="StrongPass123!",
            role="landlord",
            is_staff=True,
        )
        property_obj = Property.objects.create(name="Roster Property", landlord_email=landlord.email)
        roster_file = SimpleUploadedFile(
            "roster.csv",
            b"first_name,last_name,email,phone,room_unit_label\nRoster,Resident,roster@example.com,555-0300,Unit 12\n",
            content_type="text/csv",
        )

        self.client.login(username="roster-landlord", password="StrongPass123!")
        response = self.client.post(reverse("current_resident_roster_upload"), {
            "property": property_obj.id,
            "file": roster_file,
        })

        self.assertRedirects(response, reverse("current_resident_roster_upload"))
        roster_entry = CurrentResidentRosterEntry.objects.get(email="roster@example.com")
        self.assertEqual(roster_entry.property, property_obj)
        self.assertEqual(roster_entry.room_unit_label, "Unit 12")
        application = HousingApplication.objects.get(property=property_obj, space_label="Unit 12")
        self.assertEqual(application.full_name, "Roster Resident")
        self.assertIsNotNone(application.user)

    def test_landlord_can_upload_current_resident_roster_excel(self):
        landlord = User.objects.create_user(
            username="roster-excel-landlord",
            email="roster-excel-landlord@example.com",
            password="StrongPass123!",
            role="landlord",
            is_staff=True,
        )
        property_obj = Property.objects.create(name="Roster Excel Property", landlord_email=landlord.email)

        from openpyxl import Workbook
        workbook = Workbook()
        worksheet = workbook.active
        worksheet.append(["Name", "Email", "Phone", "Room"])
        worksheet.append(["Joe Malone", "joe@example.com", "555-0410", "L"])
        buffer = BytesIO()
        workbook.save(buffer)
        buffer.seek(0)
        roster_file = SimpleUploadedFile(
            "roster.xlsx",
            buffer.read(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        self.client.login(username="roster-excel-landlord", password="StrongPass123!")
        response = self.client.post(reverse("current_resident_roster_upload"), {
            "property": property_obj.id,
            "file": roster_file,
        })

        self.assertRedirects(response, reverse("current_resident_roster_upload"))
        roster_entry = CurrentResidentRosterEntry.objects.get(email="joe@example.com")
        self.assertEqual(roster_entry.first_name, "Joe")
        self.assertEqual(roster_entry.last_name, "Malone")
        self.assertEqual(roster_entry.room_unit_label, "L")

    def test_current_resident_roster_upload_syncs_financial_terms_to_resident_file(self):
        landlord = User.objects.create_user(
            username="roster-financial-landlord",
            email="roster-financial-landlord@example.com",
            password="StrongPass123!",
            role="landlord",
            is_staff=True,
        )
        property_obj = Property.objects.create(name="Roster Financial Property", landlord_email=landlord.email)
        roster_file = SimpleUploadedFile(
            "financial-roster.csv",
            (
                b"name,phone,unit,monthly_rent,rent_due_day,monthly_utilities,rent_balance,utility_balance,"
                b"deposit_required,deposit_held,last_month_rent_paid,last_month_rent,outstanding_balance\n"
                b"Current Resident,555-111-2222,B,650.00,1,55.00,25.00,0.00,450.00,450.00,yes,650.00,25.00\n"
            ),
            content_type="text/csv",
        )

        self.client.login(username="roster-financial-landlord", password="StrongPass123!")
        response = self.client.post(reverse("current_resident_roster_upload"), {
            "property": property_obj.id,
            "file": roster_file,
        })

        self.assertRedirects(response, reverse("current_resident_roster_upload"))
        roster_entry = CurrentResidentRosterEntry.objects.get(property=property_obj, room_unit_label="B")
        self.assertEqual(roster_entry.monthly_rent, Decimal("650.00"))
        self.assertEqual(roster_entry.deposit_held, Decimal("450.00"))
        self.assertTrue(roster_entry.last_month_rent_paid)

        room_setting = PropertyRoomRent.objects.get(property=property_obj, room_unit_label="B")
        self.assertEqual(room_setting.monthly_rent, Decimal("650.00"))
        self.assertEqual(room_setting.utility_monthly, Decimal("55.00"))
        self.assertEqual(room_setting.deposit_paid, Decimal("450.00"))

        application = HousingApplication.objects.get(property=property_obj, space_label="B")
        self.assertEqual(application.full_name, "Current Resident")
        self.assertEqual(application.monthly_rent, Decimal("650.00"))
        self.assertEqual(application.balance, Decimal("25.00"))
        self.assertEqual(application.utility_monthly, Decimal("55.00"))
        self.assertEqual(application.deposit_paid, Decimal("450.00"))
        self.assertIn("Last month rent paid/held", application.additional_notes)
        self.assertIsNotNone(application.user)
        self.assertTrue(application.user.invite_code)

    def test_current_resident_roster_upload_replaces_active_property_list(self):
        landlord = User.objects.create_user(
            username="replace-roster-landlord",
            email="replace-roster-landlord@example.com",
            password="StrongPass123!",
            role="landlord",
            is_staff=True,
        )
        property_obj = Property.objects.create(name="Replace Roster Property", landlord_email=landlord.email)
        CurrentResidentRosterEntry.objects.create(
            property=property_obj,
            first_name="Mispelled",
            last_name="Resident",
            email="old@example.com",
            room_unit_label="G",
            uploaded_by=landlord,
        )
        roster_file = SimpleUploadedFile(
            "corrected.csv",
            b"first_name,last_name,email,phone,room_unit_label\nCorrected,Resident,new@example.com,555-0301,G\n",
            content_type="text/csv",
        )

        self.client.login(username="replace-roster-landlord", password="StrongPass123!")
        response = self.client.post(reverse("current_resident_roster_upload"), {
            "property": property_obj.id,
            "file": roster_file,
        })

        self.assertRedirects(response, reverse("current_resident_roster_upload"))
        self.assertFalse(CurrentResidentRosterEntry.objects.get(email="old@example.com").is_active)
        self.assertTrue(CurrentResidentRosterEntry.objects.get(email="new@example.com").is_active)

    def test_current_resident_roster_update_same_unit_does_not_duplicate_resident_file(self):
        landlord = User.objects.create_user(
            username="roster-dedupe-landlord",
            email="roster-dedupe-landlord@example.com",
            password="StrongPass123!",
            role="landlord",
            is_staff=True,
        )
        property_obj = Property.objects.create(name="Roster Dedupe Property", landlord_email=landlord.email)
        HousingApplication.objects.create(
            property=property_obj,
            full_name="Old Name",
            phone="555-1000",
            email="old@example.com",
            age=0,
            space_type="Room",
            space_label="Room C",
            monthly_rent=Decimal("500.00"),
            balance=Decimal("0.00"),
            income_source="Existing",
            monthly_income=Decimal("0.00"),
            housing_need="Existing file",
        )
        roster_file = SimpleUploadedFile(
            "corrected.csv",
            b"name,phone,unit,monthly_rent\nCorrect Name,555-2000,C,610.00\n",
            content_type="text/csv",
        )

        self.client.login(username="roster-dedupe-landlord", password="StrongPass123!")
        response = self.client.post(reverse("current_resident_roster_upload"), {
            "property": property_obj.id,
            "file": roster_file,
        })

        self.assertRedirects(response, reverse("current_resident_roster_upload"))
        self.assertEqual(HousingApplication.objects.filter(property=property_obj).count(), 1)
        application = HousingApplication.objects.get(property=property_obj)
        self.assertEqual(application.full_name, "Correct Name")
        self.assertEqual(application.space_label, "C")
        self.assertEqual(application.monthly_rent, Decimal("610.00"))

    def test_landlord_can_view_current_resident_intake_detail_and_backup_code(self):
        landlord = User.objects.create_user(
            username="resident-intake-detail-landlord",
            email="resident-intake-detail-landlord@example.com",
            password="StrongPass123!",
            role="landlord",
            is_staff=True,
        )
        property_obj = Property.objects.create(name="Intake Detail Property", landlord_email=landlord.email)
        intake = ExistingResidentIntake.objects.create(
            property=property_obj,
            first_name="Detail",
            last_name="Resident",
            email="detail-resident@example.com",
            phone="555-0201",
            room_unit_label="Unit 8",
        )
        application = ensure_existing_resident_portal_application(intake)
        application.user.refresh_invite_code()

        self.client.login(username="resident-intake-detail-landlord", password="StrongPass123!")
        response = self.client.get(reverse("landlord_existing_resident_intake_detail", args=[intake.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Detail Resident")
        self.assertContains(response, "Unit 8")
        self.assertContains(response, application.user.invite_code)

    def test_existing_resident_intake_closes_after_property_window(self):
        property_obj = Property.objects.create(name="Older Property")
        property_obj.created_at = timezone.now() - timezone.timedelta(days=31)
        property_obj.save(update_fields=["created_at"])

        property_response = self.client.get(reverse("property_detail", args=[property_obj.id]))
        self.assertNotContains(property_response, "Existing Resident Profile")

        intake_response = self.client.get(reverse("existing_resident_intake", args=[property_obj.id]))
        self.assertRedirects(intake_response, reverse("property_detail", args=[property_obj.id]))

    def test_homepage_shows_painted_lady_profile_setup_during_intake_window(self):
        property_obj = Property.objects.create(name="The Painted Lady Inn")

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Already live at The Painted Lady Inn?")
        self.assertContains(response, reverse("existing_resident_intake", args=[property_obj.id]))

        property_obj.created_at = timezone.now() - timezone.timedelta(days=31)
        property_obj.save(update_fields=["created_at"])

        closed_response = self.client.get(reverse("home"))

        self.assertNotContains(closed_response, "Set Up My Profile")

    @override_settings(DEMO_PUBLIC_URL="https://bowlinglegacy-demo.onrender.com/demo/")
    def test_homepage_shows_public_demo_link_when_configured(self):
        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Try Demo")
        self.assertContains(response, "https://bowlinglegacy-demo.onrender.com/demo/")

    def test_admin_can_issue_property_owner_invite_from_intake(self):
        invite_admin = User.objects.create_superuser(
            username="invite-admin",
            email="invite-admin@example.com",
            password="StrongPass123!",
        )
        intake = PropertyOwnerIntake.objects.create(
            full_name="Invite Owner",
            email="invite-owner@example.com",
            phone="555-0193",
        )
        request = RequestFactory().post("/")
        request.user = invite_admin
        intake_admin = admin.site._registry[PropertyOwnerIntake]

        with patch.object(intake_admin, "message_user"):
            intake_admin.send_property_owner_portal_invites(
                request,
                PropertyOwnerIntake.objects.filter(id=intake.id),
            )

        intake.refresh_from_db()
        self.assertEqual(intake.status, "invited")
        self.assertIsNotNone(intake.user)
        self.assertTrue(intake.user.invite_code)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(intake.user.invite_code, mail.outbox[0].body)

    def test_superadmin_owner_intake_inbox_can_open_file_and_send_invite(self):
        User.objects.create_superuser(
            username="owner-intake-admin",
            email="owner-intake-admin@example.com",
            password="StrongPass123!",
            role="admin",
        )
        intake = PropertyOwnerIntake.objects.create(
            full_name="Owner Inbox User",
            company_name="Owner Inbox LLC",
            email="owner-inbox@example.com",
            phone="555-0196",
            dashboard_goals="Need reports by property.",
            needs_owner_reporting=True,
        )

        self.client.login(username="owner-intake-admin", password="StrongPass123!")

        inbox_response = self.client.get(reverse("superadmin_owner_intakes"))
        detail_response = self.client.get(reverse("superadmin_owner_intake_detail", args=[intake.id]))
        pipeline_response = self.client.post(reverse("superadmin_owner_intake_detail", args=[intake.id]), {
            "action": "update_lead_pipeline",
            "lead_stage": "demo_scheduled",
            "follow_up_date": "2026-06-18",
            "internal_notes": "Demo set for reporting workflow.",
        })
        invite_response = self.client.post(reverse("superadmin_send_owner_invite", args=[intake.id]))

        self.assertContains(inbox_response, "Owner Inbox User")
        self.assertContains(detail_response, "Need reports by property.")
        self.assertRedirects(pipeline_response, reverse("superadmin_owner_intake_detail", args=[intake.id]))
        self.assertRedirects(invite_response, reverse("superadmin_owner_intake_detail", args=[intake.id]))
        intake.refresh_from_db()
        self.assertEqual(intake.lead_stage, "demo_scheduled")
        self.assertEqual(str(intake.follow_up_date), "2026-06-18")
        self.assertEqual(intake.internal_notes, "Demo set for reporting workflow.")
        self.assertEqual(intake.status, "invited")
        self.assertIsNotNone(intake.user)
        self.assertTrue(intake.user.invite_code)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(intake.user.invite_code, mail.outbox[0].body)

    def test_staff_can_create_property_blog_and_approve_comment(self):
        staff_user = User.objects.create_user(
            username="staff-blog",
            email="staff-blog@example.com",
            password="StrongPass123!",
            role="landlord",
            is_staff=True,
        )
        property_obj = Property.objects.create(name="Blog Property", landlord_email="staff-blog@example.com")

        self.client.login(username="staff-blog", password="StrongPass123!")

        response = self.client.post(reverse("property_blog_create"), {
            "property": property_obj.id,
            "title": "Owner update",
            "body": "This is a property-specific update.",
        })

        self.assertRedirects(response, reverse("property_blog_manager"))
        post = BlogPost.objects.get(title="Owner update")
        self.assertEqual(post.property, property_obj)
        self.assertEqual(post.author, staff_user)

        comment = BlogComment.objects.create(
            post=post,
            name="Owner",
            email="owner@example.com",
            comment="Please approve this.",
            approved=False,
        )

        response = self.client.post(reverse("approve_blog_comment", args=[comment.id]))

        self.assertRedirects(response, reverse("property_blog_manager"))
        comment.refresh_from_db()
        self.assertTrue(comment.approved)

    def test_property_blog_post_notifies_property_residents(self):
        staff_user = User.objects.create_user(
            username="staff-blog-notify",
            email="staff-blog-notify@example.com",
            password="StrongPass123!",
            role="landlord",
            is_staff=True,
        )
        resident_user = User.objects.create_user(username="blog-resident", password="StrongPass123!", role="tenant")
        property_obj = Property.objects.create(name="Blog Notify Property", landlord_email=staff_user.email)
        application = HousingApplication.objects.create(
            property=property_obj,
            user=resident_user,
            full_name="Blog Resident",
            phone="555-0222",
            email="blog-resident@example.com",
            age=46,
            income_source="Employment",
            monthly_income=Decimal("3000.00"),
            housing_need="Current resident.",
            sms_opted_in=False,
        )

        self.client.login(username="staff-blog-notify", password="StrongPass123!")
        response = self.client.post(reverse("property_blog_create"), {
            "property": property_obj.id,
            "title": "Water notice",
            "body": "Water will be off briefly.",
        })

        self.assertRedirects(response, reverse("property_blog_manager"))
        self.assertEqual(mail.outbox[0].to, ["blog-resident@example.com"])
        self.assertIn(reverse("tenant_dashboard"), mail.outbox[0].body)
        sms_log = SmsMessageLog.objects.get(application=application)
        self.assertEqual(sms_log.status, "skipped_no_consent")

    def test_staff_can_delete_pending_blog_comment(self):
        staff_user = User.objects.create_user(
            username="staff-delete-comment",
            email="staff-delete-comment@example.com",
            password="StrongPass123!",
            role="landlord",
            is_staff=True,
        )
        property_obj = Property.objects.create(name="Comment Property", landlord_email="staff-delete-comment@example.com")
        post = BlogPost.objects.create(
            property=property_obj,
            author=staff_user,
            title="Resident notice",
            body="Private property update.",
        )
        comment = BlogComment.objects.create(
            post=post,
            name="Bad Comment",
            email="bad-comment@example.com",
            comment="Do not approve.",
            approved=False,
        )

        self.client.login(username="staff-delete-comment", password="StrongPass123!")

        response = self.client.post(reverse("delete_blog_comment", args=[comment.id]))

        self.assertRedirects(response, reverse("property_blog_manager"))
        self.assertFalse(BlogComment.objects.filter(id=comment.id).exists())

    def test_homepage_only_shows_public_blog_posts(self):
        property_obj = Property.objects.create(name="Private Blog Property")
        BlogPost.objects.create(title="Public update", body="Public news.")
        BlogPost.objects.create(property=property_obj, title="Private resident update", body="Residents only.")

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Public update")
        self.assertNotContains(response, "Private resident update")

    def test_owner_and_landlord_blog_forms_only_offer_assigned_properties(self):
        owner_property = Property.objects.create(name="Owner Property", owner_email="owner-blog@example.com")
        landlord_property = Property.objects.create(name="Landlord Property", landlord_email="landlord-blog@example.com")
        Property.objects.create(name="Other Property", owner_email="other@example.com", landlord_email="other@example.com")
        BlogPost.objects.create(title="Public website note", body="Superuser only.")

        User.objects.create_user(
            username="owner-blog",
            email="owner-blog@example.com",
            password="StrongPass123!",
            role="property_owner",
        )
        User.objects.create_user(
            username="landlord-blog",
            email="landlord-blog@example.com",
            password="StrongPass123!",
            role="landlord",
            is_staff=True,
        )

        self.client.login(username="owner-blog", password="StrongPass123!")
        owner_form = self.client.get(reverse("property_blog_create"))
        owner_manager = self.client.get(reverse("property_blog_manager"))
        self.assertContains(owner_form, owner_property.name)
        self.assertNotContains(owner_form, landlord_property.name)
        self.assertNotContains(owner_manager, "Public website note")

        self.client.logout()
        self.client.login(username="landlord-blog", password="StrongPass123!")
        landlord_form = self.client.get(reverse("property_blog_create"))
        landlord_manager = self.client.get(reverse("property_blog_manager"))
        self.assertContains(landlord_form, landlord_property.name)
        self.assertNotContains(landlord_form, owner_property.name)
        self.assertNotContains(landlord_manager, "Public website note")

    def test_property_blog_is_private_to_residents_of_that_property(self):
        property_obj = Property.objects.create(name="Resident Blog Property")
        BlogPost.objects.create(property=property_obj, title="Residents only notice", body="Private update.")

        anonymous_response = self.client.get(reverse("property_detail", args=[property_obj.id]))
        self.assertEqual(anonymous_response.status_code, 200)
        self.assertNotContains(anonymous_response, "Residents only notice")

        resident_user = User.objects.create_user(
            username="property-resident",
            email="property-resident@example.com",
            password="StrongPass123!",
            role="tenant",
        )
        HousingApplication.objects.create(
            property=property_obj,
            user=resident_user,
            full_name="Property Resident",
            phone="555-0133",
            email="property-resident@example.com",
            age=45,
            income_source="Employment",
            monthly_income=Decimal("2500.00"),
            housing_need="Current resident.",
        )

        self.client.login(username="property-resident", password="StrongPass123!")
        resident_response = self.client.get(reverse("property_detail", args=[property_obj.id]))
        dashboard_response = self.client.get(reverse("tenant_dashboard"))

        self.assertEqual(resident_response.status_code, 200)
        self.assertNotContains(resident_response, "Residents only notice")
        self.assertContains(dashboard_response, "Residents only notice")

    def test_resident_property_blog_does_not_show_manager_link_or_other_property_updates(self):
        resident_property = Property.objects.create(name="Resident Property")
        other_property = Property.objects.create(name="Other Property")
        BlogPost.objects.create(property=resident_property, title="Resident update", body="Private notice.")
        BlogPost.objects.create(property=other_property, title="Other resident update", body="Do not show.")
        resident_user = User.objects.create_user(
            username="dashboard-blog-resident",
            email="dashboard-blog-resident@example.com",
            password="StrongPass123!",
            role="tenant",
        )
        HousingApplication.objects.create(
            property=resident_property,
            user=resident_user,
            full_name="Dashboard Blog Resident",
            phone="555-0134",
            email="dashboard-blog-resident@example.com",
            age=46,
            income_source="Employment",
            monthly_income=Decimal("2500.00"),
            housing_need="Current resident.",
        )

        self.client.login(username="dashboard-blog-resident", password="StrongPass123!")

        detail_response = self.client.get(reverse("property_detail", args=[resident_property.id]))
        dashboard_response = self.client.get(reverse("tenant_dashboard"))

        self.assertNotContains(detail_response, "Manage Blog")
        self.assertContains(dashboard_response, "Resident update")
        self.assertNotContains(dashboard_response, "Other resident update")

    def test_resident_balance_history_and_requests_pages_are_resident_scoped(self):
        resident_user = User.objects.create_user(
            username="balance-resident",
            email="balance-resident@example.com",
            password="StrongPass123!",
            role="tenant",
        )
        application = HousingApplication.objects.create(
            user=resident_user,
            full_name="Balance Resident",
            phone="555-0135",
            email="balance-resident@example.com",
            age=44,
            income_source="Employment",
            monthly_income=Decimal("2500.00"),
            housing_need="Current resident.",
            balance=Decimal("725.00"),
            utility_balance=Decimal("66.00"),
        )
        Payment.objects.create(
            application=application,
            payment_type="rent",
            amount=Decimal("725.00"),
            status="completed",
        )
        ResidentMessage.objects.create(
            application=application,
            message_type="maintenance",
            subject="Sink request",
            message="Check the sink.",
        )

        self.client.login(username="balance-resident", password="StrongPass123!")

        balance_response = self.client.get(reverse("resident_balance_detail"))
        history_response = self.client.get(reverse("resident_payment_history"))
        requests_response = self.client.get(reverse("resident_requests"))

        self.assertContains(balance_response, "Rent Due")
        self.assertContains(balance_response, "Pay Utilities")
        self.assertContains(history_response, "Payment History")
        self.assertContains(requests_response, "Sink request")

    def test_resident_can_reply_only_to_own_message(self):
        resident_user = User.objects.create_user(
            username="reply-resident",
            email="reply-resident@example.com",
            password="StrongPass123!",
            role="tenant",
        )
        other_user = User.objects.create_user(
            username="other-reply-resident",
            email="other-reply-resident@example.com",
            password="StrongPass123!",
            role="tenant",
        )
        application = HousingApplication.objects.create(
            user=resident_user,
            full_name="Reply Resident",
            phone="555-0137",
            email="reply-resident@example.com",
            age=43,
            income_source="Employment",
            monthly_income=Decimal("2500.00"),
            housing_need="Current resident.",
        )
        other_application = HousingApplication.objects.create(
            user=other_user,
            full_name="Other Reply Resident",
            phone="555-0138",
            email="other-reply-resident@example.com",
            age=43,
            income_source="Employment",
            monthly_income=Decimal("2500.00"),
            housing_need="Current resident.",
        )
        resident_message = ResidentMessage.objects.create(
            application=application,
            subject="My request",
            message="My private request.",
        )
        other_message = ResidentMessage.objects.create(
            application=other_application,
            subject="Other request",
            message="Other private request.",
        )

        self.client.login(username="reply-resident", password="StrongPass123!")
        response = self.client.post(reverse("resident_requests"), {
            "message_id": resident_message.id,
            "reply_body": "Here is my reply.",
        })

        self.assertRedirects(response, reverse("resident_requests"))
        self.assertTrue(ResidentMessageReply.objects.filter(message=resident_message, body="Here is my reply.").exists())

        blocked_response = self.client.post(reverse("resident_requests"), {
            "message_id": other_message.id,
            "reply_body": "Trying to reply.",
        })
        self.assertEqual(blocked_response.status_code, 404)
        self.assertFalse(ResidentMessageReply.objects.filter(message=other_message).exists())

    def test_resident_upload_rejects_lease_document_type(self):
        resident_user = User.objects.create_user(
            username="document-upload-resident",
            email="document-upload-resident@example.com",
            password="StrongPass123!",
            role="tenant",
        )
        HousingApplication.objects.create(
            user=resident_user,
            full_name="Document Upload Resident",
            phone="555-0136",
            email="document-upload-resident@example.com",
            age=43,
            income_source="Employment",
            monthly_income=Decimal("2500.00"),
            housing_need="Current resident.",
        )
        document = SimpleUploadedFile("lease.pdf", b"not a signed lease", content_type="application/pdf")

        self.client.login(username="document-upload-resident", password="StrongPass123!")
        response = self.client.post(reverse("upload_resident_document"), {
            "document_type": "lease",
            "name": "Lease Upload",
            "file": document,
        })

        self.assertRedirects(response, reverse("tenant_dashboard"))
        self.assertFalse(ApplicantDocument.objects.filter(name="Lease Upload").exists())

    def test_resident_message_notification_replies_to_resident_email(self):
        resident_user = User.objects.create_user(
            username="message-notification-resident",
            email="message-resident@example.com",
            password="StrongPass123!",
            role="tenant",
        )
        property_obj = Property.objects.create(name="Message Notification Property", owner_email="owner@example.com")
        HousingApplication.objects.create(
            user=resident_user,
            property=property_obj,
            full_name="Message Resident",
            phone="555-0137",
            email="message-resident@example.com",
            age=43,
            income_source="Employment",
            monthly_income=Decimal("2500.00"),
            housing_need="Current resident.",
            space_label="B",
        )

        self.client.login(username="message-notification-resident", password="StrongPass123!")
        response = self.client.post(reverse("submit_resident_message"), {
            "message_type": "general",
            "subject": "Question",
            "message": "Can you review this?",
        })

        self.assertRedirects(response, reverse("tenant_dashboard"))
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["owner@example.com"])
        self.assertEqual(mail.outbox[0].reply_to, ["message-resident@example.com"])
        self.assertIn("Open secure portal thread:", mail.outbox[0].body)
        self.assertIn("Replying to this email will go to the resident", mail.outbox[0].body)

    def test_resident_document_notification_replies_to_resident_email(self):
        resident_user = User.objects.create_user(
            username="document-notification-resident",
            email="document-reply@example.com",
            password="StrongPass123!",
            role="tenant",
        )
        property_obj = Property.objects.create(name="Document Notification Property", owner_email="owner@example.com")
        HousingApplication.objects.create(
            user=resident_user,
            property=property_obj,
            full_name="Document Reply Resident",
            phone="555-0138",
            email="document-reply@example.com",
            age=43,
            income_source="Employment",
            monthly_income=Decimal("2500.00"),
            housing_need="Current resident.",
            space_label="C",
        )
        document = SimpleUploadedFile("id.pdf", b"resident id", content_type="application/pdf")

        self.client.login(username="document-notification-resident", password="StrongPass123!")
        response = self.client.post(reverse("upload_resident_document"), {
            "document_type": "id",
            "name": "Resident ID",
            "file": document,
        })

        self.assertRedirects(response, reverse("tenant_dashboard"))
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["owner@example.com"])
        self.assertEqual(mail.outbox[0].reply_to, ["document-reply@example.com"])

    def test_staff_can_mark_uploaded_document_reviewed(self):
        staff_user = User.objects.create_user(
            username="staff",
            email="staff@example.com",
            password="StrongPass123!",
            role="landlord",
            is_staff=True,
        )
        property_obj = Property.objects.create(name="Document Property", landlord_email=staff_user.email)
        application = HousingApplication.objects.create(
            property=property_obj,
            full_name="Document Resident",
            phone="555-0106",
            email="document@example.com",
            age=47,
            income_source="Employment",
            monthly_income=Decimal("3000.00"),
            housing_need="Needs review.",
        )
        document = ApplicantDocument.objects.create(
            application=application,
            document_type="id",
            name="Review Me",
            file="applicant_documents/review.pdf",
            status="uploaded",
            landlord_notified=False,
        )

        self.client.login(username="staff", password="StrongPass123!")

        response = self.client.post(reverse("mark_document_reviewed", args=[document.id]))

        self.assertRedirects(response, reverse("landlord_dashboard"))
        document.refresh_from_db()
        self.assertTrue(document.landlord_notified)

    def test_cleanup_test_portal_data_dry_run_deletes_nothing(self):
        application = HousingApplication.objects.create(
            full_name="Dry Run Resident",
            phone="555-0107",
            email="dryrun@example.com",
            age=48,
            income_source="Employment",
            monthly_income=Decimal("3000.00"),
            housing_need="Test record.",
        )
        Payment.objects.create(
            application=application,
            payment_type="rent",
            payment_method="cash",
            amount=Decimal("1.00"),
            status="completed",
        )

        output = StringIO()
        call_command("cleanup_test_portal_data", stdout=output)

        self.assertIn("Dry run only", output.getvalue())
        self.assertEqual(HousingApplication.objects.count(), 1)
        self.assertEqual(Payment.objects.count(), 1)

    def test_cleanup_test_portal_data_confirm_preserves_named_email_and_staff(self):
        staff_user = User.objects.create_user(
            username="owner",
            email="michael@bowlinglegacy.com",
            password="StrongPass123!",
            role="landlord",
            is_staff=True,
        )
        superuser = User.objects.create_superuser(
            username="system-owner",
            email="superowner@example.com",
            password="StrongPass123!",
        )
        tenant_user = User.objects.create_user(
            username="test-tenant",
            email="tenant@example.com",
            role="tenant",
        )
        preserved_user = User.objects.create_user(
            username="preserved-tenant",
            email="keep@example.com",
            role="tenant",
        )
        test_application = HousingApplication.objects.create(
            full_name="Delete Me",
            phone="555-0108",
            email="tenant@example.com",
            age=49,
            user=tenant_user,
            income_source="Employment",
            monthly_income=Decimal("3000.00"),
            housing_need="Test record.",
        )
        preserved_application = HousingApplication.objects.create(
            full_name="Keep Me",
            phone="555-0109",
            email="keep@example.com",
            age=50,
            user=preserved_user,
            income_source="Employment",
            monthly_income=Decimal("3000.00"),
            housing_need="Real record.",
        )
        ResidentMessage.objects.create(
            application=test_application,
            subject="Delete message",
            message="Test",
        )
        ApplicantDocument.objects.create(
            application=test_application,
            document_type="id",
            name="Delete document",
            file="applicant_documents/delete.pdf",
        )
        Payment.objects.create(
            application=test_application,
            payment_type="rent",
            payment_method="cash",
            amount=Decimal("1.00"),
            status="completed",
        )

        output = StringIO()
        call_command(
            "cleanup_test_portal_data",
            "--confirm",
            "--preserve-email",
            "keep@example.com",
            stdout=output,
        )

        self.assertIn("Cleanup complete", output.getvalue())
        self.assertFalse(HousingApplication.objects.filter(id=test_application.id).exists())
        self.assertFalse(User.objects.filter(id=tenant_user.id).exists())
        self.assertTrue(HousingApplication.objects.filter(id=preserved_application.id).exists())
        self.assertTrue(User.objects.filter(id=preserved_user.id).exists())
        self.assertTrue(User.objects.filter(id=staff_user.id).exists())
        self.assertTrue(User.objects.filter(id=superuser.id).exists())
        self.assertEqual(ResidentMessage.objects.count(), 0)
        self.assertEqual(ApplicantDocument.objects.count(), 0)
        self.assertEqual(Payment.objects.count(), 0)

    def test_cleanup_preserves_felicia_name_and_only_completed_one_dollar_payment(self):
        felicia = HousingApplication.objects.create(
            full_name="Felicia Valdez",
            phone="555-0110",
            email="felicia@example.com",
            age=51,
            income_source="Employment",
            monthly_income=Decimal("3000.00"),
            housing_need="Real application.",
        )
        felicia_document = SignedDocument.objects.create(
            application=felicia,
            document_type="lease",
            title="Felicia Lease Agreement",
            locked=True,
        )
        paid_application = HousingApplication.objects.create(
            full_name="Real Payment Resident",
            phone="555-0111",
            email="paid@example.com",
            age=52,
            income_source="Employment",
            monthly_income=Decimal("3000.00"),
            housing_need="Real payment.",
        )
        test_application = HousingApplication.objects.create(
            full_name="Delete Test",
            phone="555-0112",
            email="delete@example.com",
            age=53,
            income_source="Employment",
            monthly_income=Decimal("3000.00"),
            housing_need="Delete me.",
        )
        kept_payment = Payment.objects.create(
            application=paid_application,
            payment_type="rent",
            payment_method="stripe_card",
            amount=Decimal("1.00"),
            status="completed",
        )
        Payment.objects.create(
            application=test_application,
            payment_type="rent",
            payment_method="cash",
            amount=Decimal("20.00"),
            status="completed",
        )

        output = StringIO()
        call_command(
            "cleanup_test_portal_data",
            "--confirm",
            "--preserve-only-completed-one-dollar-payment",
            "--keep-users",
            stdout=output,
        )

        self.assertTrue(HousingApplication.objects.filter(id=felicia.id).exists())
        self.assertTrue(SignedDocument.objects.filter(id=felicia_document.id).exists())
        self.assertTrue(HousingApplication.objects.filter(id=paid_application.id).exists())
        self.assertFalse(HousingApplication.objects.filter(id=test_application.id).exists())
        self.assertTrue(Payment.objects.filter(id=kept_payment.id).exists())

    def test_cleanup_deletes_only_explicitly_named_test_properties(self):
        abc_property = Property.objects.create(name="ABC CO PROPERTY")
        newtest_property = Property.objects.create(name="newtest fake property")
        real_property = Property.objects.create(name="Painted Lady Inn")

        preview = StringIO()
        call_command(
            "cleanup_test_portal_data",
            "--delete-property-name",
            "ABC CO PROPERTY",
            "--delete-property-name",
            "newtest fake property",
            stdout=preview,
        )

        self.assertIn("Properties selected by exact name: 2", preview.getvalue())
        self.assertTrue(Property.objects.filter(id=abc_property.id).exists())
        self.assertTrue(Property.objects.filter(id=newtest_property.id).exists())

        call_command(
            "cleanup_test_portal_data",
            "--confirm",
            "--delete-property-name",
            "ABC CO PROPERTY",
            "--delete-property-name",
            "newtest fake property",
        )

        self.assertFalse(Property.objects.filter(id=abc_property.id).exists())
        self.assertFalse(Property.objects.filter(id=newtest_property.id).exists())
        self.assertTrue(Property.objects.filter(id=real_property.id).exists())

    def test_issue_painted_lady_platform_lease_command_preserves_signed_lease(self):
        property_obj = Property.objects.create(name="The Painted Lady Inn")
        application = HousingApplication.objects.create(
            property=property_obj,
            full_name="Lease Update Resident",
            phone="555-0500",
            email="lease-update@example.com",
            age=50,
            income_source="Employment",
            monthly_income=Decimal("3000.00"),
            housing_need="Current resident.",
        )
        signed_lease = SignedDocument.objects.create(
            application=application,
            document_type="lease",
            title="Original Signed Lease",
            locked=True,
        )

        output = StringIO()
        call_command("issue_painted_lady_platform_lease", "--confirm", stdout=output)

        self.assertTrue(SignedDocument.objects.filter(id=signed_lease.id, locked=True).exists())
        self.assertTrue(
            SignedDocument.objects.filter(
                application=application,
                document_type="lease",
                title="Resident Lease Agreement - June 2026 Platform Update",
                locked=False,
            ).exists()
        )
        self.assertIn("Issued 1 lease update document", output.getvalue())
