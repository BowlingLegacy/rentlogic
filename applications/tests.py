from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from accounts.models import InviteCode, Profile

from .models import HousingApplication


class CreateTenantTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="owner",
            email="owner@example.com",
            password="pass12345",
        )
        Profile.objects.create(user=self.owner, role="owner", status="new")

        self.application = HousingApplication.objects.create(
            full_name="Test Resident",
            phone="555-111-2222",
            email="resident@example.com",
            age=35,
            monthly_income=2500,
        )

    def test_owner_approval_creates_onboarding_invite(self):
        self.client.login(username="owner", password="pass12345")

        response = self.client.post(
            f"{reverse('create_tenant')}?application={self.application.id}",
            {
                "monthly_rent": "1200.00",
                "balance": "0.00",
                "rent_due_day": "1",
                "deposit_required": "1200.00",
                "deposit_paid": "100.00",
                "utility_monthly": "85.00",
                "utility_balance": "0.00",
                "space_type": "Suite",
                "space_label": "101",
                "additional_notes": "Approved locally.",
            },
        )

        self.assertEqual(response.status_code, 200)

        self.application.refresh_from_db()
        self.assertEqual(self.application.status, "onboarding")
        self.assertIsNotNone(self.application.onboarding_invite)
        self.assertEqual(InviteCode.objects.count(), 1)
        self.assertContains(response, self.application.onboarding_invite.code)

    def test_existing_invite_is_reused(self):
        invite = InviteCode.objects.create(
            full_name=self.application.full_name,
            email=self.application.email,
            phone=self.application.phone,
            role_to_create="user",
            created_by=self.owner,
        )
        self.application.onboarding_invite = invite
        self.application.save()

        self.client.login(username="owner", password="pass12345")

        self.client.post(
            f"{reverse('create_tenant')}?application={self.application.id}",
            {
                "monthly_rent": "1200.00",
                "balance": "0.00",
                "rent_due_day": "1",
                "deposit_required": "1200.00",
                "deposit_paid": "100.00",
                "utility_monthly": "85.00",
                "utility_balance": "0.00",
                "space_type": "Suite",
                "space_label": "101",
            },
        )

        self.application.refresh_from_db()
        self.assertEqual(self.application.onboarding_invite, invite)
        self.assertEqual(InviteCode.objects.count(), 1)
