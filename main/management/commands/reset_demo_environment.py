from datetime import date, datetime
from decimal import Decimal

from django.apps import apps
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files import File
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.text import slugify
from django.utils import timezone

from main.models import (
    BlogPost,
    CurrentResidentRosterEntry,
    ExpenseCategory,
    FinancialEntry,
    FinancialUpload,
    HousingApplication,
    Payment,
    Property,
    PropertyOwnerIntake,
    PropertyRoomRent,
    PropertyUtilityVendor,
    ResidentMessage,
    User,
)


class Command(BaseCommand):
    help = "Reset the isolated demo database and seed it with temporary sample property data."

    def add_arguments(self, parser):
        parser.add_argument("--confirm", action="store_true", help="Required to perform the reset.")

    def handle(self, *args, **options):
        if not getattr(settings, "DEMO_MODE", False):
            raise CommandError("Refusing to reset data because DEMO_MODE is not enabled.")

        if not options["confirm"]:
            raise CommandError("Run again with --confirm to reset and reseed the demo environment.")

        with transaction.atomic():
            self.delete_main_app_data()
            self.seed_demo_data()

        self.stdout.write(self.style.SUCCESS("Demo environment reset complete."))
        self.stdout.write("Demo entry URL: /demo/")
        self.stdout.write(f"Demo admin username: {settings.DEMO_ADMIN_USERNAME}")

    def delete_main_app_data(self):
        for model in reversed(list(apps.get_app_config("main").get_models())):
            model.objects.all().delete()

    def seed_demo_data(self):
        admin = User.objects.create_superuser(
            username=settings.DEMO_ADMIN_USERNAME,
            email="demo-admin@example.com",
            password="DemoPass123!",
            role="admin",
        )
        primary_owner = User.objects.create_user(
            username="demo-owner-olivia",
            email="olivia.owner@example.com",
            password="DemoPass123!",
            role="property_owner",
            first_name="Olivia",
            last_name="Owner",
        )
        second_owner = User.objects.create_user(
            username="demo-owner-marcus",
            email="marcus.owner@example.com",
            password="DemoPass123!",
            role="property_owner",
            first_name="Marcus",
            last_name="Morgan",
        )
        primary_landlord = User.objects.create_user(
            username="demo-landlord-larry",
            email="larry.landlord@example.com",
            password="DemoPass123!",
            role="landlord",
            first_name="Larry",
            last_name="Landlord",
            is_staff=True,
        )
        second_landlord = User.objects.create_user(
            username="demo-landlord-nina",
            email="nina.landlord@example.com",
            password="DemoPass123!",
            role="landlord",
            first_name="Nina",
            last_name="Nelson",
            is_staff=True,
        )

        property_specs = [
            {
                "name": "Demo Ridge Apartments",
                "address": "100 Sample Way, Medford, OR",
                "owner": primary_owner,
                "landlord": primary_landlord,
                "description": "Twenty-four unit garden-style demo property with mixed rent collection and utility billing.",
                "availability_status": "available",
                "availability_message": "Two demo units available",
                "rent_amount": Decimal("1250.00"),
                "deposit_amount": Decimal("900.00"),
                "utilities_cost": "Resident electric, shared water billed monthly",
                "utility_vendors": [
                    ("Electric", "Pacific Power", "https://www.pacificpower.net", "888-221-7070"),
                ],
                "image": "photo03.JPG",
                "rooms": [
                    ("101", "Avery Brooks", "avery@example.com", Decimal("1250.00"), Decimal("75.00"), Decimal("900.00"), Decimal("900.00"), Decimal("0.00"), Decimal("0.00")),
                    ("102", "Bianca Carter", "bianca@example.com", Decimal("1325.00"), Decimal("75.00"), Decimal("900.00"), Decimal("450.00"), Decimal("1325.00"), Decimal("75.00")),
                    ("103", "Camille Lane", "camille@example.com", Decimal("1280.00"), Decimal("75.00"), Decimal("900.00"), Decimal("900.00"), Decimal("0.00"), Decimal("0.00")),
                    ("104", "Dorian Mills", "dorian@example.com", Decimal("1295.00"), Decimal("75.00"), Decimal("900.00"), Decimal("900.00"), Decimal("0.00"), Decimal("0.00")),
                    ("201", "Carlos Diaz", "carlos@example.com", Decimal("1195.00"), Decimal("70.00"), Decimal("800.00"), Decimal("800.00"), Decimal("0.00"), Decimal("0.00")),
                    ("202", "Dana Ellis", "dana@example.com", Decimal("1425.00"), Decimal("85.00"), Decimal("950.00"), Decimal("950.00"), Decimal("425.00"), Decimal("0.00")),
                    ("203", "Elena Foster", "elena@example.com", Decimal("1375.00"), Decimal("80.00"), Decimal("950.00"), Decimal("950.00"), Decimal("0.00"), Decimal("0.00")),
                    ("204", "Finn Grant", "finn@example.com", Decimal("1390.00"), Decimal("80.00"), Decimal("950.00"), Decimal("475.00"), Decimal("0.00"), Decimal("0.00")),
                    ("301", "Gia Holloway", "gia@example.com", Decimal("1450.00"), Decimal("85.00"), Decimal("1000.00"), Decimal("1000.00"), Decimal("0.00"), Decimal("0.00")),
                    ("302", "Holden Kim", "holden@example.com", Decimal("1475.00"), Decimal("85.00"), Decimal("1000.00"), Decimal("1000.00"), Decimal("0.00"), Decimal("0.00")),
                    ("303", "Iris Mason", "iris@example.com", Decimal("1510.00"), Decimal("90.00"), Decimal("1000.00"), Decimal("500.00"), Decimal("0.00"), Decimal("90.00")),
                    ("304", "Jonah Price", "jonah@example.com", Decimal("1525.00"), Decimal("90.00"), Decimal("1000.00"), Decimal("1000.00"), Decimal("0.00"), Decimal("0.00")),
                ],
                "summary": [
                    (1, "10500.00", "4350.00", "2800.00"),
                    (2, "10675.00", "4625.00", "2800.00"),
                    (3, "10820.00", "4405.00", "2800.00"),
                    (4, "10910.00", "4920.00", "2800.00"),
                    (5, "11100.00", "4515.00", "2800.00"),
                ],
            },
            {
                "name": "Cedar Market Lofts",
                "address": "42 Cedar Market Lane, Eugene, OR",
                "owner": primary_owner,
                "landlord": primary_landlord,
                "description": "Mixed-use demo property with retail suites below residential lofts.",
                "availability_status": "waitlist",
                "availability_message": "Retail waitlist open",
                "rent_amount": Decimal("1850.00"),
                "deposit_amount": Decimal("1200.00"),
                "utilities_cost": "Commercial utilities reimbursed monthly",
                "utility_vendors": [
                    ("Electric", "Eugene Water & Electric Board", "https://www.eweb.org", "541-685-7000"),
                    ("Trash", "Sanipac", "https://www.sanipac.com", "541-736-3600"),
                ],
                "image": "photo01.JPG",
                "rooms": [
                    ("Retail A", "Harper Foods LLC", "harper-foods@example.com", Decimal("2600.00"), Decimal("185.00"), Decimal("1800.00"), Decimal("1800.00"), Decimal("0.00"), Decimal("0.00")),
                    ("Retail B", "Juniper Salon LLC", "juniper-salon@example.com", Decimal("2350.00"), Decimal("170.00"), Decimal("1700.00"), Decimal("1700.00"), Decimal("0.00"), Decimal("0.00")),
                    ("Retail C", "Market Books LLC", "market-books@example.com", Decimal("2150.00"), Decimal("160.00"), Decimal("1600.00"), Decimal("800.00"), Decimal("0.00"), Decimal("0.00")),
                    ("Loft 1A", "Nora Quinn", "nora.quinn@example.com", Decimal("1695.00"), Decimal("90.00"), Decimal("1100.00"), Decimal("1100.00"), Decimal("0.00"), Decimal("0.00")),
                    ("Loft 1B", "Miles Reed", "miles.reed@example.com", Decimal("1710.00"), Decimal("90.00"), Decimal("1100.00"), Decimal("1100.00"), Decimal("0.00"), Decimal("0.00")),
                    ("Loft 2B", "Eli Turner", "eli.turner@example.com", Decimal("1725.00"), Decimal("95.00"), Decimal("1100.00"), Decimal("1100.00"), Decimal("0.00"), Decimal("0.00")),
                    ("Loft 3C", "Maya Stone", "maya.stone@example.com", Decimal("1810.00"), Decimal("95.00"), Decimal("1200.00"), Decimal("600.00"), Decimal("0.00"), Decimal("95.00")),
                    ("Loft 4D", "Parker Vale", "parker.vale@example.com", Decimal("1865.00"), Decimal("100.00"), Decimal("1200.00"), Decimal("1200.00"), Decimal("0.00"), Decimal("0.00")),
                ],
                "summary": [
                    (1, "15950.00", "6425.00", "4200.00"),
                    (2, "16125.00", "6810.00", "4200.00"),
                    (3, "16400.00", "6015.00", "4200.00"),
                    (4, "16675.00", "7050.00", "4200.00"),
                    (5, "16920.00", "6290.00", "4200.00"),
                ],
            },
            {
                "name": "Pine Street Villas",
                "address": "760 Pine Street, Grants Pass, OR",
                "owner": second_owner,
                "landlord": second_landlord,
                "description": "Small villa-style demo community with owner reporting and maintenance tracking.",
                "availability_status": "full",
                "availability_message": "Currently full",
                "rent_amount": Decimal("1540.00"),
                "deposit_amount": Decimal("1000.00"),
                "utilities_cost": "Residents pay utilities directly",
                "utility_vendors": [
                    ("Power", "Pacific Power", "https://www.pacificpower.net", "888-221-7070"),
                    ("Water/Sewer", "City Utility Billing", "https://www.grantspassoregon.gov", "541-450-6035"),
                    ("Trash", "Republic Services", "https://www.republicservices.com", "541-779-4161"),
                ],
                "image": "photo02.JPG",
                "rooms": [
                    ("Villa 1", "Noah Reed", "noah.reed@example.com", Decimal("1500.00"), Decimal("0.00"), Decimal("1000.00"), Decimal("1000.00"), Decimal("0.00"), Decimal("0.00")),
                    ("Villa 2", "Isla Green", "isla.green@example.com", Decimal("1540.00"), Decimal("0.00"), Decimal("1000.00"), Decimal("1000.00"), Decimal("0.00"), Decimal("0.00")),
                    ("Villa 3", "Owen Hall", "owen.hall@example.com", Decimal("1585.00"), Decimal("0.00"), Decimal("1000.00"), Decimal("750.00"), Decimal("585.00"), Decimal("0.00")),
                    ("Villa 4", "Priya Imani", "priya.imani@example.com", Decimal("1600.00"), Decimal("0.00"), Decimal("1000.00"), Decimal("1000.00"), Decimal("0.00"), Decimal("0.00")),
                    ("Villa 5", "Quentin James", "quentin.james@example.com", Decimal("1625.00"), Decimal("0.00"), Decimal("1050.00"), Decimal("1050.00"), Decimal("0.00"), Decimal("0.00")),
                    ("Villa 6", "Riley Knox", "riley.knox@example.com", Decimal("1640.00"), Decimal("0.00"), Decimal("1050.00"), Decimal("525.00"), Decimal("0.00"), Decimal("0.00")),
                    ("Villa 7", "Sofia Long", "sofia.long@example.com", Decimal("1660.00"), Decimal("0.00"), Decimal("1050.00"), Decimal("1050.00"), Decimal("0.00"), Decimal("0.00")),
                    ("Villa 8", "Theo Morgan", "theo.morgan@example.com", Decimal("1685.00"), Decimal("0.00"), Decimal("1100.00"), Decimal("1100.00"), Decimal("0.00"), Decimal("0.00")),
                ],
                "summary": [
                    (1, "9250.00", "3125.00", "2500.00"),
                    (2, "9250.00", "2980.00", "2500.00"),
                    (3, "9350.00", "3410.00", "2500.00"),
                    (4, "9350.00", "3225.00", "2500.00"),
                    (5, "9465.00", "3640.00", "2500.00"),
                ],
            },
            {
                "name": "Harbor View Senior Living",
                "address": "18 Harbor View Drive, Coos Bay, OR",
                "owner": second_owner,
                "landlord": second_landlord,
                "description": "Senior housing demo property focused on resident communication and simple payments.",
                "availability_status": "available",
                "availability_message": "One studio available",
                "rent_amount": Decimal("980.00"),
                "deposit_amount": Decimal("650.00"),
                "utilities_cost": "Flat shared utilities",
                "utility_vendors": [],
                "image": "photo03.JPG",
                "rooms": [
                    ("Studio A", "Ruth Mills", "ruth.mills@example.com", Decimal("980.00"), Decimal("60.00"), Decimal("650.00"), Decimal("650.00"), Decimal("0.00"), Decimal("0.00")),
                    ("Studio B", "Frank Lee", "frank.lee@example.com", Decimal("1025.00"), Decimal("60.00"), Decimal("650.00"), Decimal("650.00"), Decimal("0.00"), Decimal("0.00")),
                    ("Studio C", "Grace Paul", "grace.paul@example.com", Decimal("995.00"), Decimal("60.00"), Decimal("650.00"), Decimal("325.00"), Decimal("0.00"), Decimal("60.00")),
                    ("Studio D", "Helen Ortiz", "helen.ortiz@example.com", Decimal("1010.00"), Decimal("60.00"), Decimal("650.00"), Decimal("650.00"), Decimal("0.00"), Decimal("0.00")),
                    ("Studio E", "Ivan Perez", "ivan.perez@example.com", Decimal("1040.00"), Decimal("60.00"), Decimal("675.00"), Decimal("675.00"), Decimal("0.00"), Decimal("0.00")),
                    ("Studio F", "June Ramos", "june.ramos@example.com", Decimal("1065.00"), Decimal("65.00"), Decimal("675.00"), Decimal("675.00"), Decimal("0.00"), Decimal("0.00")),
                    ("Studio G", "Kara Santos", "kara.santos@example.com", Decimal("1080.00"), Decimal("65.00"), Decimal("700.00"), Decimal("350.00"), Decimal("0.00"), Decimal("65.00")),
                    ("Studio H", "Leo Ward", "leo.ward@example.com", Decimal("1095.00"), Decimal("65.00"), Decimal("700.00"), Decimal("700.00"), Decimal("0.00"), Decimal("0.00")),
                ],
                "summary": [
                    (1, "6200.00", "2480.00", "1800.00"),
                    (2, "6260.00", "2555.00", "1800.00"),
                    (3, "6260.00", "2305.00", "1800.00"),
                    (4, "6320.00", "2715.00", "1800.00"),
                    (5, "6320.00", "2525.00", "1800.00"),
                ],
            },
        ]

        now = timezone.now()
        all_demo_residents = []
        for property_index, spec in enumerate(property_specs, start=1):
            property_obj = Property.objects.create(
                name=spec["name"],
                address=spec["address"],
                owner_email=spec["owner"].email,
                landlord_email=spec["landlord"].email,
                description=spec["description"],
                availability_status=spec["availability_status"],
                availability_message=spec["availability_message"],
                rent_amount=spec["rent_amount"],
                deposit_amount=spec["deposit_amount"],
                utilities_cost=spec["utilities_cost"],
                charges_application_fee=True,
                application_fee_amount=Decimal("45.00"),
                requires_background_check=True,
                background_check_fee_amount=Decimal("35.00"),
            )
            self.attach_demo_property_photo(property_obj, spec["image"])

            for sort_order, (service_type, provider_name, setup_url, phone) in enumerate(spec.get("utility_vendors", []), start=1):
                PropertyUtilityVendor.objects.create(
                    property=property_obj,
                    service_type=service_type,
                    provider_name=provider_name,
                    setup_url=setup_url,
                    phone=phone,
                    sort_order=sort_order,
                )

            demo_residents = []
            for room_index, (room, name, email, rent, utilities, deposit_required, deposit_paid, rent_balance, utility_balance) in enumerate(spec["rooms"], start=1):
                first_name, last_name = name.split(" ", 1)
                PropertyRoomRent.objects.create(
                    property=property_obj,
                    room_unit_label=room,
                    monthly_rent=rent,
                    utility_monthly=utilities,
                    deposit_required=deposit_required,
                    deposit_paid=deposit_paid,
                )
                CurrentResidentRosterEntry.objects.create(
                    property=property_obj,
                    first_name=first_name,
                    last_name=last_name,
                    email=email,
                    phone=f"541-555-{property_index}{room_index:03d}",
                    room_unit_label=room,
                    uploaded_by=admin,
                )
                username_slug = slugify(f"{spec['name']} {room}")[:40]
                tenant_user = User.objects.create_user(
                    username=f"demo-{username_slug}",
                    email=email,
                    password="DemoPass123!",
                    role="tenant",
                )
                application = HousingApplication.objects.create(
                    property=property_obj,
                    user=tenant_user,
                    full_name=name,
                    phone=f"541-555-{property_index + 10}{room_index:03d}",
                    email=email,
                    age=30 + room_index,
                    space_type="Unit",
                    space_label=room,
                    monthly_rent=rent,
                    balance=rent_balance,
                    rent_due_day=1,
                    lease_start_date=date(2025, min(room_index, 12), 1),
                    deposit_required=deposit_required,
                    deposit_paid=deposit_paid,
                    utility_monthly=utilities,
                    utility_balance=utility_balance,
                    income_source="Employment",
                    monthly_income=rent * Decimal("3.4"),
                    housing_need="Demo resident profile.",
                    sobriety_acknowledgment=True,
                    unconditional_regard_acknowledgment=True,
                )
                demo_residents.append(application)
                all_demo_residents.append(application)

            for month in [1, 2, 3, 4, 5]:
                service_month = date(2026, month, 1)
                for application in demo_residents:
                    if application.balance > 0 and month == 5:
                        continue
                    Payment.objects.create(
                        application=application,
                        payment_type="rent",
                        payment_method="ach",
                        description=f"Demo {service_month.strftime('%B')} rent",
                        amount=application.monthly_rent,
                        status="completed",
                        received_at=timezone.make_aware(datetime(2026, month, min(application.rent_due_day, 28), 9, 0)),
                        service_month=service_month,
                        recorded_by=admin,
                    )
                    if application.utility_monthly > 0:
                        if application.utility_balance > 0 and month == 5:
                            continue
                        Payment.objects.create(
                            application=application,
                            payment_type="utility",
                            payment_method="ach",
                            description=f"Demo {service_month.strftime('%B')} utilities",
                            amount=application.utility_monthly,
                            status="completed",
                            received_at=timezone.make_aware(datetime(2026, month, min(application.rent_due_day, 28), 9, 10)),
                            service_month=service_month,
                            recorded_by=admin,
                        )

            upload = FinancialUpload.objects.create(
                property=property_obj,
                name=f"{property_obj.name} Demo T12 Summary",
                file=ContentFile(b"demo,summary\n", name=f"{slugify(property_obj.name)}_demo_t12_summary.csv"),
                parsed_at=now,
                notes="Seeded demo summary data. This database resets automatically.",
            )
            for month, income, expenses, debt in spec["summary"]:
                FinancialEntry.objects.create(upload=upload, property_name=property_obj.name, sheet_name="Demo Summary", row_number=month, year=2026, month=month, entry_type="income", category="Rent and Other Income", amount=Decimal(income))
                FinancialEntry.objects.create(upload=upload, property_name=property_obj.name, sheet_name="Demo Summary", row_number=month + 20, year=2026, month=month, entry_type="operating_expense", category="Operating Expenses", amount=Decimal(expenses))
                FinancialEntry.objects.create(upload=upload, property_name=property_obj.name, sheet_name="Demo Summary", row_number=month + 40, year=2026, month=month, entry_type="debt_service", category="Debt Service", amount=Decimal(debt))

            BlogPost.objects.create(
                property=property_obj,
                author=spec["landlord"],
                title=f"{property_obj.name} Community Update",
                body="This is a private demo property blog post for residents, landlords, and owners.",
            )

        for name in ["Repairs", "Utilities", "Insurance", "Capital Improvements"]:
            ExpenseCategory.objects.create(name=name, entry_type="capital_expense" if name == "Capital Improvements" else "operating_expense", created_by=admin)

        ResidentMessage.objects.create(
            application=all_demo_residents[1],
            message_type="maintenance",
            subject="Kitchen sink leak",
            message="Demo maintenance message: small leak under the kitchen sink.",
            status="submitted",
        )
        ResidentMessage.objects.create(
            application=all_demo_residents[-1],
            message_type="general",
            subject="Parking question",
            message="Demo resident question: where should guests park during the weekend?",
            status="submitted",
        )
        PropertyOwnerIntake.objects.create(
            full_name="Morgan Multifamily",
            company_name="Morgan Multifamily Group",
            email="owner-lead@example.com",
            phone="541-555-0199",
            property_count=3,
            total_units=86,
            property_types="multifamily",
            current_software="Spreadsheet and legacy accounting export",
            current_pain_points="Needs easier rent roll, T-12, owner reporting, receipt tracking, and resident communication.",
            desired_reports="T-12, Rent Roll, NOI, Utility Trends, Vendor Expense, Valuation Estimate",
            status="submitted",
        )

    def attach_demo_property_photo(self, property_obj, image_name):
        image_path = settings.BASE_DIR / "static" / "images" / image_name
        if not image_path.exists():
            return

        with image_path.open("rb") as image_file:
            property_obj.photo.save(f"demo-{slugify(property_obj.name)}-{image_name}", File(image_file), save=True)
