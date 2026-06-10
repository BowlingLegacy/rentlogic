from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import (
    OwnerFinancialUploadForm,
    OwnerLandlordInviteForm,
    OwnerPropertyForm,
    OwnerPropertyOnboardingDocumentsForm,
)
from .invite_utils import create_pending_portal_user, send_portal_access_invite_email
from .models import FinancialUpload, Property, PropertyImage, HousingApplication, Payment, ResidentMessage
from .permissions import can_access_owner_dashboard, is_super_admin, is_assistant_admin


@login_required
@user_passes_test(can_access_owner_dashboard)
def property_owner_dashboard(request):
    properties = owner_properties_for(request.user)

    property_cards = []
    portfolio_monthly_rent = Decimal("0.00")
    portfolio_balances_due = Decimal("0.00")
    portfolio_utilities_due = Decimal("0.00")
    portfolio_deposits_held = Decimal("0.00")
    portfolio_collected = Decimal("0.00")
    total_residents = 0
    total_open_messages = 0

    for property_obj in properties:
        residents = HousingApplication.objects.filter(property=property_obj).order_by("space_label", "full_name")
        resident_count = residents.count()
        open_messages = ResidentMessage.objects.filter(application__property=property_obj, status="submitted").count()
        completed_payments = Payment.objects.filter(application__property=property_obj, status="completed")

        monthly_rent = residents.aggregate(total=Sum("monthly_rent"))["total"] or Decimal("0.00")
        balances_due = residents.aggregate(total=Sum("balance"))["total"] or Decimal("0.00")
        utilities_due = residents.aggregate(total=Sum("utility_balance"))["total"] or Decimal("0.00")
        deposits_held = residents.aggregate(total=Sum("deposit_paid"))["total"] or Decimal("0.00")
        total_collected = completed_payments.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

        portfolio_monthly_rent += monthly_rent
        portfolio_balances_due += balances_due
        portfolio_utilities_due += utilities_due
        portfolio_deposits_held += deposits_held
        portfolio_collected += total_collected
        total_residents += resident_count
        total_open_messages += open_messages

        property_cards.append({
            "property": property_obj,
            "resident_count": resident_count,
            "monthly_rent": monthly_rent,
            "balances_due": balances_due,
            "utilities_due": utilities_due,
            "deposits_held": deposits_held,
            "total_collected": total_collected,
            "open_messages": open_messages,
        })

    recent_messages = ResidentMessage.objects.filter(
        application__property__in=properties
    ).select_related(
        "application", "application__property"
    ).order_by("-created_at")[:12]

    return render(request, "property_owner_dashboard.html", {
        "property_cards": property_cards,
        "properties": properties,
        "total_properties": properties.count(),
        "total_residents": total_residents,
        "portfolio_monthly_rent": portfolio_monthly_rent,
        "portfolio_balances_due": portfolio_balances_due,
        "portfolio_utilities_due": portfolio_utilities_due,
        "portfolio_deposits_held": portfolio_deposits_held,
        "portfolio_collected": portfolio_collected,
        "total_open_messages": total_open_messages,
        "recent_messages": recent_messages,
    })


@login_required
@user_passes_test(can_access_owner_dashboard)
def owner_onboarding_wizard(request):
    properties = owner_properties_for(request.user).prefetch_related(
        "onboarding_documents",
        "room_rents",
        "financial_uploads",
        "rental_listings",
    )

    property_steps = []
    for property_obj in properties:
        resident_count = HousingApplication.objects.filter(property=property_obj, user__isnull=False).count()
        applicant_count = HousingApplication.objects.filter(property=property_obj, user__isnull=True).count()
        onboarding_docs = property_obj.onboarding_documents.all()
        room_count = property_obj.room_rents.filter(is_active=True).count()
        financial_upload_count = property_obj.financial_uploads.count()
        listing_count = property_obj.rental_listings.count()

        steps = [
            {
                "label": "Property profile",
                "complete": bool(property_obj.name and property_obj.address and property_obj.rent_amount),
                "detail": "Name, address, rent, deposit, utilities, fees, screening, and insurance settings.",
                "url": "owner_property_create",
                "button": "Add Another Property",
            },
            {
                "label": "Onboarding documents",
                "complete": onboarding_docs.filter(document_type="application").exists() and onboarding_docs.filter(document_type="lease").exists(),
                "detail": f"{onboarding_docs.count()} document(s) uploaded. Application and lease are the required starting point.",
                "url": "owner_property_onboarding_documents",
                "url_args": [property_obj.id],
                "button": "Upload Documents",
            },
            {
                "label": "Units and rent setup",
                "complete": room_count > 0,
                "detail": f"{room_count} unit/rent row(s) configured.",
                "url": "landlord_rent_setup_property",
                "url_args": [property_obj.id],
                "button": "Set Up Units",
            },
            {
                "label": "Landlord or manager",
                "complete": bool(property_obj.landlord_email),
                "detail": property_obj.landlord_email or "No landlord or property manager assigned yet.",
                "url": "owner_landlord_invite",
                "button": "Invite Landlord",
            },
            {
                "label": "Residents and applicants",
                "complete": resident_count > 0,
                "detail": f"{resident_count} resident(s) and {applicant_count} applicant file(s) connected.",
                "url": "property_detail",
                "url_args": [property_obj.id],
                "button": "Open Property Page",
            },
            {
                "label": "Financial source files",
                "complete": financial_upload_count > 0,
                "detail": f"{financial_upload_count} financial upload(s) on file.",
                "url": "owner_financial_upload",
                "button": "Upload Financials",
            },
            {
                "label": "Vacancy listing",
                "complete": listing_count > 0,
                "detail": f"{listing_count} listing record(s) created.",
                "url": "rental_listing_create",
                "button": "Create Listing",
            },
        ]

        completed_count = sum(1 for step in steps if step["complete"])
        property_steps.append({
            "property": property_obj,
            "steps": steps,
            "completed_count": completed_count,
            "total_count": len(steps),
            "percent_complete": int(completed_count / len(steps) * 100),
        })

    return render(request, "owner_onboarding_wizard.html", {
        "properties": properties,
        "property_steps": property_steps,
    })


def owner_properties_for(user):
    if is_super_admin(user) or is_assistant_admin(user):
        return Property.objects.all().order_by("name")

    return Property.objects.filter(owner_email__iexact=user.email).order_by("name")


@login_required
@user_passes_test(can_access_owner_dashboard)
def owner_property_create(request):
    form = OwnerPropertyForm(request.POST or None, request.FILES or None)

    if request.method == "POST" and form.is_valid():
        property_obj = form.save(commit=False)
        property_obj.owner_email = request.user.email
        property_obj.save()

        PropertyImage.objects.bulk_create([
            PropertyImage(property=property_obj, image=image)
            for image in form.cleaned_data["gallery_images"]
        ])
        form.save_utility_vendors(property_obj)

        messages.success(request, f"{property_obj.name} was added to your owner dashboard.")
        return redirect("owner_property_onboarding_documents", property_id=property_obj.id)

    return render(request, "owner_property_form.html", {"form": form})


@login_required
@user_passes_test(can_access_owner_dashboard)
def owner_property_onboarding_documents(request, property_id):
    property_obj = get_object_or_404(owner_properties_for(request.user), id=property_id)
    form = OwnerPropertyOnboardingDocumentsForm(request.POST or None, request.FILES or None)

    if request.method == "POST" and form.is_valid():
        form.save(property_obj)
        messages.success(
            request,
            "Property onboarding files were saved for conversion and property setup review.",
        )
        return redirect("property_owner_dashboard")

    documents = property_obj.onboarding_documents.all()
    return render(request, "owner_property_onboarding_documents.html", {
        "form": form,
        "property": property_obj,
        "documents": documents,
    })


@login_required
@user_passes_test(can_access_owner_dashboard)
def owner_landlord_invite(request):
    properties = owner_properties_for(request.user)
    form = OwnerLandlordInviteForm(request.POST or None, properties=properties)

    if request.method == "POST" and form.is_valid():
        intake = form.save()
        property_obj = form.cleaned_data["property"]
        property_obj.landlord_email = intake.email
        property_obj.save(update_fields=["landlord_email"])

        user = create_pending_portal_user(intake.full_name, intake.email, "landlord", intake.id)
        user.refresh_invite_code()
        intake.user = user
        intake.status = "invited"
        intake.invite_sent_at = timezone.now()
        intake.save(update_fields=["user", "status", "invite_sent_at"])

        try:
            send_portal_access_invite_email(user, intake.full_name, "Landlord")
        except Exception as exc:
            messages.warning(request, f"Landlord setup code created, but email failed: {exc}")
        else:
            messages.success(request, "Landlord setup invite email sent.")

        messages.info(request, f"Backup landlord setup code: {user.invite_code}")
        return redirect("property_owner_dashboard")

    return render(request, "owner_landlord_invite.html", {
        "form": form,
        "properties": properties,
    })


@login_required
@user_passes_test(can_access_owner_dashboard)
def owner_financial_upload(request):
    properties = owner_properties_for(request.user)
    form = OwnerFinancialUploadForm(request.POST or None, request.FILES or None, properties=properties)

    if request.method == "POST" and form.is_valid():
        upload = form.save()
        messages.success(request, "Financial document uploaded for review and import processing.")
        return redirect("owner_financial_upload")

    uploads = FinancialUpload.objects.filter(property__in=properties).select_related("property").order_by("-uploaded_at")
    return render(request, "owner_financial_upload.html", {
        "form": form,
        "uploads": uploads,
        "properties": properties,
    })
