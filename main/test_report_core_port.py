from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import (
    AccountingPeriod,
    AccountingReceipt,
    AccountingReceiptSplit,
    ExpenseCategory,
    FinancialEntry,
    FinancialUpload,
    HousingApplication,
    LandlordIntake,
    Payment,
    Property,
)
from .views import financial_entries_for_properties, payment_month_allocations, t12_report_rows


User = get_user_model()


@override_settings(STATICFILES_STORAGE="django.contrib.staticfiles.storage.StaticFilesStorage")
class SharedReportCorePortTests(TestCase):
    def setUp(self):
        self.landlord = User.objects.create_user(
            username="report-port", email="report-port@example.com", password="StrongPass123!",
            role="landlord", is_staff=True,
        )
        LandlordIntake.objects.create(user=self.landlord, email=self.landlord.email, status="registered")
        self.a = Property.objects.create(name="Port A", landlord_email=self.landlord.email)
        self.b = Property.objects.create(name="Port B", landlord_email=self.landlord.email)
        self.client.force_login(self.landlord)

    def upload(self, property_obj, name, ledger_scope="property"):
        return FinancialUpload.objects.create(
            property=property_obj, ledger_scope=ledger_scope, name=name,
            file=SimpleUploadedFile(f"{name}.csv", b"date,amount\n"),
        )

    def entry(self, upload, property_obj, amount, **overrides):
        values = {
            "upload": upload,
            "property": property_obj,
            "ledger_scope": "property" if property_obj else upload.ledger_scope,
            "property_name": property_obj.name if property_obj else "Company",
            "sheet_name": "Summary",
            "row_number": FinancialEntry.objects.count() + 1,
            "year": 2026,
            "month": 1,
            "entry_type": "income",
            "category": "Rent",
            "amount": amount,
        }
        values.update(overrides)
        return FinancialEntry.objects.create(**values)

    def resident(self, property_obj, name):
        return HousingApplication.objects.create(
            property=property_obj, full_name=name, phone="555-0100",
            email=f"{name.lower().replace(' ', '.')}@example.com", age=40,
            income_source="Synthetic", monthly_income=Decimal("2000.00"),
            housing_need="Synthetic", resident_file_status="active", space_label="A",
            monthly_rent=Decimal("650.00"), utility_monthly=Decimal("0.00"),
            lease_start_date=date(2026, 1, 1),
        )

    def test_multi_month_cent_allocation(self):
        payment = Payment.objects.create(
            application=self.resident(self.a, "Allocation Resident"), payment_type="rent",
            payment_method="cash", status="completed", amount=Decimal("100.00"),
            service_month=date(2026, 1, 1), months_covered=3,
        )
        self.assertEqual(list(payment_month_allocations(payment)), [
            (date(2026, 1, 1), Decimal("33.33")),
            (date(2026, 2, 1), Decimal("33.33")),
            (date(2026, 3, 1), Decimal("33.34")),
        ])

    def test_portfolio_precedence_is_resolved_per_property(self):
        self.entry(self.upload(self.a, "a-summary"), self.a, Decimal("1000.00"))
        Payment.objects.create(
            application=self.resident(self.b, "Portal Resident"), payment_type="rent",
            payment_method="cash", status="completed", amount=Decimal("700.00"),
            service_month=date(2026, 1, 1),
        )
        months, totals = t12_report_rows(
            self.landlord, 2026, Property.objects.filter(id__in=[self.a.id, self.b.id])
        )
        self.assertEqual(months[0]["spreadsheet_income"], Decimal("1000.00"))
        self.assertEqual(months[0]["online_income"], Decimal("700.00"))
        self.assertEqual(totals["total_income"], Decimal("1700.00"))

    def test_stable_row_attribution_excludes_company_and_upload_owner_leakage(self):
        mixed = self.upload(self.a, "mixed-bank", ledger_scope="bank")
        self.entry(mixed, self.a, Decimal("100.00"), entry_type="operating_expense", category="Repairs")
        self.entry(mixed, self.b, Decimal("200.00"), entry_type="operating_expense", category="Repairs")
        self.entry(mixed, None, Decimal("300.00"), ledger_scope="company", entry_type="operating_expense")
        a_months, _ = t12_report_rows(self.landlord, 2026, Property.objects.filter(id=self.a.id))
        b_months, _ = t12_report_rows(self.landlord, 2026, Property.objects.filter(id=self.b.id))
        self.assertEqual(a_months[0]["operating_expenses"], Decimal("100.00"))
        self.assertEqual(b_months[0]["operating_expenses"], Decimal("200.00"))

    def test_legacy_name_fallback_requires_unique_property_name(self):
        unique = self.entry(self.upload(self.a, "legacy"), None, Decimal("10.00"), property=None,
                            ledger_scope="property", property_name=self.a.name)
        duplicate_one = Property.objects.create(name="Duplicate", landlord_email=self.landlord.email)
        Property.objects.create(name="Duplicate", landlord_email=self.landlord.email)
        ambiguous = self.entry(self.upload(duplicate_one, "ambiguous"), None, Decimal("20.00"), property=None,
                               ledger_scope="property", property_name="Duplicate")
        scoped = financial_entries_for_properties(Property.objects.filter(id__in=[self.a.id, duplicate_one.id]))
        self.assertIn(unique, scoped)
        self.assertNotIn(ambiguous, scoped)

    def test_reversed_dates_do_not_generate_report(self):
        response = self.client.get(reverse("custom_reports"), {
            "report_type": "payment_summary", "start_date": "2026-03-02", "end_date": "2026-02-28",
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["generated"])
        self.assertContains(response, "Start date must be on or before end date")

    def test_payment_csv_neutralizes_formula_text_and_uses_reference_precedence(self):
        payment = Payment.objects.create(
            application=self.resident(self.a, "=FORMULA"), payment_type="rent",
            payment_method="cash", status="completed", amount=Decimal("50.00"),
            service_month=date(2026, 1, 1), reference_number="+manual-ref",
            stripe_payment_intent="pi_fallback", stripe_session_id="cs_fallback",
        )
        response = self.client.get(reverse("export_payment_log_csv") + "?month=all")
        content = response.content.decode()
        self.assertEqual(response.status_code, 200)
        self.assertIn("'=FORMULA", content)
        self.assertIn("'+manual-ref", content)
        self.assertNotIn("pi_fallback", content)
        self.assertIn(str(payment.id), content)

    def test_vendor_total_counts_only_approved_and_each_receipt_lineage_once(self):
        power, _ = ExpenseCategory.objects.get_or_create(name="Power", defaults={"entry_type": "operating_expense"})
        repairs, _ = ExpenseCategory.objects.get_or_create(name="Repairs", defaults={"entry_type": "operating_expense"})

        def receipt(vendor, amount, status, category=None):
            return AccountingReceipt.objects.create(
                property=self.a, vendor=vendor,
                receipt_file=SimpleUploadedFile(f"{vendor}.txt", b"synthetic receipt"),
                receipt_date=date(2026, 4, 15), category=category, amount=amount, status=status,
            )

        receipt("Approved Unsplit", Decimal("50.00"), "approved", power)
        split_receipt = receipt("Approved Split", Decimal("999.00"), "approved")
        AccountingReceiptSplit.objects.create(receipt=split_receipt, category=power, amount=Decimal("60.00"))
        AccountingReceiptSplit.objects.create(receipt=split_receipt, category=repairs, amount=Decimal("40.00"))
        receipt("Pending Vendor", Decimal("20.00"), "needs_review", power)
        receipt("Ignored Duplicate", Decimal("30.00"), "ignored", power)

        response = self.client.get(reverse("custom_reports"), {
            "report_type": "vendor_expense", "property_id": self.a.id,
            "start_date": "2026-04-01", "end_date": "2026-04-30",
        })
        self.assertEqual(response.context["totals"], {
            "Approved Expense Total": Decimal("150.00"),
            "Pending / Needs Review (excluded)": Decimal("20.00"),
            "Ignored / Duplicate (excluded)": Decimal("30.00"),
        })
        self.assertNotIn(Decimal("999.00"), [row[3] for row in response.context["report_rows"]])

    def test_valuation_fails_closed_without_explicit_period_close_provenance(self):
        self.entry(self.upload(self.a, "partial-year"), self.a, Decimal("1200.00"), month=1)
        response = self.client.get(reverse("custom_reports"), {
            "report_type": "valuation_estimate", "property_id": self.a.id,
            "start_date": "2026-01-01",
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["report_rows"]), 1)
        row = response.context["report_rows"][0]
        self.assertEqual(row[1], "Not calculated")
        self.assertEqual(row[3], "Not calculated")
        self.assertIn("0 of 12 accounting months explicitly closed", row[4])
        self.assertIn("missing Jan, Feb, Mar, Apr, May, Jun, Jul, Aug, Sep, Oct, Nov, Dec", row[4])
        self.assertIn("Valuation remains intentionally disabled", row[4])
        self.assertNotContains(response, "months annualized")

    def test_valuation_stays_disabled_with_twelve_closed_periods(self):
        for month in range(1, 13):
            AccountingPeriod.objects.create(
                property=self.a,
                year=2026,
                month=month,
                status="closed",
                closed_by=self.landlord,
            )
        self.entry(self.upload(self.a, "closed-year"), self.a, Decimal("1200.00"), month=1)

        response = self.client.get(reverse("custom_reports"), {
            "report_type": "valuation_estimate", "property_id": self.a.id,
            "start_date": "2026-01-01",
        })

        self.assertEqual(response.status_code, 200)
        row = response.context["report_rows"][0]
        self.assertEqual(row[1], "Not calculated")
        self.assertEqual(row[3], "Not calculated")
        self.assertIn("12 of 12 accounting months explicitly closed", row[4])
        self.assertIn("Valuation remains intentionally disabled", row[4])
        self.assertNotContains(response, "months annualized")

    @patch("main.views.timezone.localdate", return_value=date(2026, 1, 31))
    def test_projection_uses_elapsed_months_only(self, _today):
        Payment.objects.create(
            application=self.resident(self.a, "Annual Allocation"), payment_type="rent",
            payment_method="cash", status="completed", amount=Decimal("1200.00"),
            service_month=date(2026, 1, 1), months_covered=12,
        )
        _months, totals = t12_report_rows(self.landlord, 2026, Property.objects.filter(id=self.a.id))
        self.assertEqual(totals["net_cash_flow"], Decimal("1200.00"))
        self.assertEqual(totals["projected_annual_cash_flow"], Decimal("1200.00"))
