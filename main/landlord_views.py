from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.conf import settings
from django.core.mail import send_mail
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.text import slugify

from .forms import LandlordCreateTenantForm
from .models import HousingApplication, SignedDocument, User
from .views import find_room_rent_setting, prorated_monthly_charge, staff_managed_properties, staff_required


def send_resident_invite_email(application):
    if not application.user or not application.user.email:
        return False

    if not application.user.invite_code or application.user.invite_code_used_at:
        application.user.refresh_invite_code()

    send_mail(
        "Your RentalReadyPro Resident Portal Access Code",
        f"""Hello {application.full_name},

Your RentalReadyPro resident portal access code is:

{application.user.invite_code}

Portal setup:
https://rentalreadypro.com/enter-invite-code/

This code is single-use and expires 30 minutes after it is issued. If it expires, request a new code from the invite-code page.
If this email is not in your inbox, check your junk or spam folder.

Thank you,
RentalReadyPro
""",
        getattr(settings, "DEFAULT_FROM_EMAIL", None),
        [application.user.email],
        fail_silently=False,
    )

    return True


def ensure_onboarding_documents(application):
    document_specs = [
        ("lease", "Resident Lease Agreement"),
        ("emergency_contact", "Emergency Contact Sheet"),
        ("painted_lady_acknowledgment", "Property Acknowledgment"),
    ]

    for document_type, title in document_specs:
        document, _ = SignedDocument.objects.get_or_create(
            application=application,
            document_type=document_type,
            defaults={
                "title": title,
                "lease_sent_date": timezone.localdate(),
                "landlord_name": "Michael Bowling",
                "landlord_signature": "Michael Bowling",
            },
        )

        if not document.locked:
            document.title = title
            document.lease_sent_date = document.lease_sent_date or timezone.localdate()
            document.landlord_name = document.landlord_name or "Michael Bowling"
            document.landlord_signature = document.landlord_signature or "Michael Bowling"
            document.save()


def apply_room_rent_setting_to_application(application, form_data):
    space_label = form_data.get("space_label", "")
    room_setting = find_room_rent_setting(application.property, space_label)

    monthly_rent = form_data.get("monthly_rent") or 0
    utility_monthly = form_data.get("utility_monthly") or 0
    deposit_required = form_data.get("deposit_required") or 0
    deposit_paid = form_data.get("deposit_paid") or 0
    rent_due_day = form_data.get("rent_due_day") or 1

    if room_setting:
        monthly_rent = room_setting.monthly_rent
        utility_monthly = room_setting.utility_monthly
        deposit_required = room_setting.deposit_required
        deposit_paid = room_setting.deposit_paid
        rent_due_day = room_setting.rent_due_day

    return {
        "room_setting": room_setting,
        "monthly_rent": monthly_rent,
        "utility_monthly": utility_monthly,
        "deposit_required": deposit_required,
        "deposit_paid": deposit_paid,
        "rent_due_day": rent_due_day,
    }


@login_required
@user_passes_test(staff_required)
def create_tenant(request):
    application_id = request.GET.get("application")

    if not application_id:
        messages.warning(request, "Choose an application before creating a resident file.")
        return redirect("landlord_dashboard")

    application = get_object_or_404(
        HousingApplication,
        id=application_id,
    )

    if application.property_id not in set(staff_managed_properties(request.user).values_list("id", flat=True)):
        messages.error(request, "That resident file is not assigned to your property workspace.")
        return redirect("landlord_dashboard")

    if request.method == "POST":
        form = LandlordCreateTenantForm(request.POST)

        if form.is_valid():
            room_values = apply_room_rent_setting_to_application(application, form.cleaned_data)
            monthly_rent = room_values["monthly_rent"]
            utility_monthly = room_values["utility_monthly"]
            lease_start_date = form.cleaned_data.get("lease_start_date")
            move_in_rent_charge = prorated_monthly_charge(monthly_rent, lease_start_date)
            move_in_utility_charge = prorated_monthly_charge(utility_monthly, lease_start_date)

            application.space_type = form.cleaned_data.get("space_type", "")
            application.space_label = form.cleaned_data.get("space_label", "")
            application.monthly_rent = monthly_rent
            application.balance = move_in_rent_charge
            application.rent_due_day = room_values["rent_due_day"]
            application.lease_start_date = lease_start_date
            application.move_in_rent_charge = move_in_rent_charge
            application.move_in_utility_charge = move_in_utility_charge
            application.deposit_required = room_values["deposit_required"]
            application.deposit_paid = room_values["deposit_paid"]
            application.deposit_payment_plan = form.cleaned_data.get("deposit_payment_plan") or "paid_in_full"
            application.utility_monthly = utility_monthly
            application.utility_balance = move_in_utility_charge
            application.additional_notes = form.cleaned_data.get("additional_notes") or ""
            move_in_note = (
                f"Move-in charges calculated from lease start date: "
                f"rent ${move_in_rent_charge}, utilities ${move_in_utility_charge}. "
                f"Regular monthly rent remains ${monthly_rent}; regular monthly utilities remain ${utility_monthly}."
            )
            if room_values["room_setting"]:
                move_in_note += f" Rent setup was pulled from room/unit {room_values['room_setting'].room_unit_label}."
            application.additional_notes = f"{application.additional_notes}\n\n{move_in_note}".strip()

            created_user = None

            if not application.user:
                base_username = slugify(application.full_name) or "resident"
                username = f"{base_username}-{application.id}"

                counter = 1
                original_username = username

                while User.objects.filter(username=username).exists():
                    counter += 1
                    username = f"{original_username}-{counter}"

                created_user = User.objects.create_user(
                    username=username,
                    email=application.email,
                    password=None,
                    role="tenant",
                    is_staff=False,
                    is_superuser=False,
                )
                created_user.refresh_invite_code()

                application.user = created_user

            application.save()
            if application.user and not application.user.has_usable_password():
                application.user.refresh_invite_code()
            ensure_onboarding_documents(application)

            email_sent = False
            email_error = ""

            try:
                email_sent = send_resident_invite_email(application)
            except Exception as exc:
                email_error = str(exc)

            if email_sent:
                messages.success(
                    request,
                    "Application approved and resident onboarding invite email sent.",
                )
            else:
                messages.warning(
                    request,
                    "Application approved, but the invite email was not sent. Use the backup invite code below.",
                )

            return render(request, "landlord_create_tenant_success.html", {
                "application": application,
                "created_user": application.user,
                "email_sent": email_sent,
                "email_error": email_error,
            })

    else:
        room_setting = find_room_rent_setting(application.property, application.space_label)
        form = LandlordCreateTenantForm(initial={
            "monthly_rent": room_setting.monthly_rent if room_setting else application.monthly_rent,
            "balance": application.balance,
            "deposit_required": room_setting.deposit_required if room_setting else application.deposit_required,
            "deposit_paid": room_setting.deposit_paid if room_setting else application.deposit_paid,
            "deposit_payment_plan": application.deposit_payment_plan,
            "utility_monthly": room_setting.utility_monthly if room_setting else application.utility_monthly,
            "utility_balance": application.utility_balance,
            "space_type": application.space_type,
            "space_label": application.space_label,
            "rent_due_day": room_setting.rent_due_day if room_setting else application.rent_due_day,
        })

    return render(request, "landlord_create_tenant.html", {
        "form": form,
        "application": application,
    })

