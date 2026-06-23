from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import (
    OwnerFinancialUploadForm,
    OwnerLandlordInviteForm,
    OwnerPropertyForm,
    OwnerPropertyOnboardingDocumentsForm,
    StripePaymentConfigurationForm,
)
from .invite_utils import create_pending_portal_user, send_portal_access_invite_email
from .models import ApplicantDocument, CurrentResidentRosterEntry, FinancialUpload, OwnerBillingAccount, Property, PropertyImage, HousingApplication, Payment, ResidentMessage, StripePaymentConfiguration
from .permissions import can_access_owner_dashboard, is_super_admin, is_assistant_admin


def effective_stripe_configuration_for_property(property_obj):
    property_config = getattr(property_obj, "stripe_payment_configuration", None)
    if property_config:
        return property_config

    owner_email = (property_obj.owner_email or "").strip()
    if owner_email:
        owner_config = (
            StripePaymentConfiguration.objects
            .filter(property__isnull=True, owner_email__iexact=owner_email)
            .order_by("-updated_at")
            .first()
        )
        if owner_config:
            return owner_config

    return None


def payment_setup_summary(property_obj):
    config = effective_stripe_configuration_for_property(property_obj)
    if config:
        return {
            "config": config,
            "label": config.get_account_mode_display(),
            "status": config.get_status_display(),
            "ready": config.can_collect_online_payments,
            "connected_account": config.stripe_account_id,
        }

    platform_ready = bool(settings.STRIPE_PUBLIC_KEY and settings.STRIPE_SECRET_KEY)
    return {
        "config": None,
        "label": "Use RentalReadyPro platform Stripe account",
        "status": "Active" if platform_ready else "Missing platform keys",
        "ready": platform_ready,
        "connected_account": "",
    }


def owner_billing_summary(user):
    if not user.email:
        return None
    return OwnerBillingAccount.objects.filter(owner_email__iexact=user.email).first()


@login_required
@user_passes_test(can_access_owner_dashboard)
def property_owner_dashboard(request):
    properties = owner_properties_for(request.user)
    today = timezone.localdate()

    property_cards = []
    portfolio_monthly_rent = Decimal("0.00")
    portfolio_balances_due = Decimal("0.00")
    portfolio_utilities_due = Decimal("0.00")
    portfolio_deposits_held = Decimal("0.00")
    portfolio_collected = Decimal("0.00")
    total_residents = 0
    total_open_messages = 0

    for property_obj in properties:
        residents = (
            HousingApplication.objects
            .filter(property=property_obj, resident_file_status="active", user__isnull=False)
            .exclude(Q(space_label="") & Q(monthly_rent=Decimal("0.00")))
            .order_by("space_label", "full_name")
        )
        resident_count = residents.count()
        open_messages = ResidentMessage.objects.filter(application__property=property_obj, status="submitted").count()
        completed_payments = Payment.objects.filter(
            application__property=property_obj,
            application__resident_file_status="active",
            application__user__isnull=False,
            status="completed",
        )
        year_to_date_payments = completed_payments.filter(
            Q(service_month__year=today.year) | Q(service_month__isnull=True, received_at__year=today.year)
        )

        monthly_rent = residents.aggregate(total=Sum("monthly_rent"))["total"] or Decimal("0.00")
        balances_due = residents.aggregate(total=Sum("balance"))["total"] or Decimal("0.00")
        utilities_due = residents.aggregate(total=Sum("utility_balance"))["total"] or Decimal("0.00")
        deposits_held = residents.aggregate(total=Sum("deposit_paid"))["total"] or Decimal("0.00")
        total_collected = year_to_date_payments.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

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
            "payment_setup": payment_setup_summary(property_obj),
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
        "current_year": today.year,
        "total_open_messages": total_open_messages,
        "recent_messages": recent_messages,
        "billing_account": owner_billing_summary(request.user),
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
    portfolio_completed_steps = 0
    portfolio_total_steps = 0
    for property_obj in properties:
        resident_count = HousingApplication.objects.filter(property=property_obj, user__isnull=False).count()
        applicant_count = HousingApplication.objects.filter(property=property_obj, user__isnull=True).count()
        roster_count = CurrentResidentRosterEntry.objects.filter(property=property_obj, is_active=True).count()
        onboarding_docs = property_obj.onboarding_documents.all()
        room_count = property_obj.room_rents.filter(is_active=True).count()
        financial_upload_count = property_obj.financial_uploads.count()
        listing_count = property_obj.rental_listings.count()
        tenant_packet_count = ApplicantDocument.objects.filter(
            application__property=property_obj,
            packet_upload=True,
        ).count()
        payment_setup = payment_setup_summary(property_obj)

        steps = [
            {
                "label": "Property profile",
                "complete": bool(property_obj.name and property_obj.address and property_obj.rent_amount),
                "detail": "Name, address, rent, deposit, utilities, fees, screening, and insurance settings.",
                "url": "owner_property_create",
                "button": "Add Another Property",
                "phase": "Property",
            },
            {
                "label": "Resident roster import",
                "complete": roster_count > 0,
                "detail": f"{roster_count} approved current resident row(s) imported.",
                "url": "current_resident_roster_upload",
                "button": "Upload Roster",
                "phase": "Data",
            },
            {
                "label": "Lease and onboarding documents",
                "complete": onboarding_docs.filter(document_type="application").exists() and onboarding_docs.filter(document_type="lease").exists(),
                "detail": f"{onboarding_docs.count()} document(s) uploaded. Application and lease are the required starting point.",
                "url": "owner_property_onboarding_documents",
                "url_args": [property_obj.id],
                "button": "Upload Documents",
                "phase": "Documents",
            },
            {
                "label": "Units and rent setup",
                "complete": room_count > 0,
                "detail": f"{room_count} unit/rent row(s) configured.",
                "url": "landlord_rent_setup_property",
                "url_args": [property_obj.id],
                "button": "Set Up Units",
                "phase": "Money",
            },
            {
                "label": "Stripe payment routing",
                "complete": payment_setup["ready"],
                "detail": f"{payment_setup['label']} - {payment_setup['status']}.",
                "url": "owner_payment_settings",
                "button": "Payment Settings",
                "phase": "Money",
            },
            {
                "label": "Landlord or manager",
                "complete": bool(property_obj.landlord_email),
                "detail": property_obj.landlord_email or "No landlord or property manager assigned yet.",
                "url": "owner_landlord_invite",
                "button": "Invite Landlord",
                "phase": "Team",
            },
            {
                "label": "Residents and applicants",
                "complete": resident_count > 0,
                "detail": f"{resident_count} resident(s) and {applicant_count} applicant file(s) connected.",
                "url": "property_detail",
                "url_args": [property_obj.id],
                "button": "Open Property Page",
                "phase": "Residents",
            },
            {
                "label": "Financial source files",
                "complete": financial_upload_count > 0,
                "detail": f"{financial_upload_count} financial upload(s) on file.",
                "url": "owner_financial_upload",
                "button": "Upload Financials",
                "phase": "Reports",
            },
            {
                "label": "Vacancy listing",
                "complete": listing_count > 0,
                "detail": f"{listing_count} listing record(s) created.",
                "url": "rental_listing_create",
                "button": "Create Listing",
                "phase": "Leasing",
            },
            {
                "label": "Scanned tenant file packets",
                "complete": tenant_packet_count > 0,
                "detail": f"{tenant_packet_count} uploaded tenant packet(s) ready for OCR/review.",
                "url": "tenant_file_packet_upload",
                "button": "Upload Tenant Files",
                "phase": "Documents",
            },
            {
                "label": "Custom report templates",
                "complete": True,
                "detail": "Owners can build saved reports from resident, payment, receipt, vendor, and vacancy data.",
                "url": "custom_reports",
                "button": "Open Reports",
                "phase": "Reports",
            },
        ]

        completed_count = sum(1 for step in steps if step["complete"])
        portfolio_completed_steps += completed_count
        portfolio_total_steps += len(steps)
        property_steps.append({
            "property": property_obj,
            "steps": steps,
            "completed_count": completed_count,
            "total_count": len(steps),
            "percent_complete": int(completed_count / len(steps) * 100),
        })

    launch_steps = [
        {
            "label": "Stripe payments",
            "complete": bool(settings.STRIPE_PUBLIC_KEY and settings.STRIPE_SECRET_KEY),
            "detail": "Platform Stripe keys plus owner/property routing are required for online rent, deposit, and application fee payments.",
            "url": "owner_payment_settings",
            "button": "Payment Settings",
        },
        {
            "label": "SMS notifications",
            "complete": bool(
                getattr(settings, "TELNYX_API_KEY", "")
                and getattr(settings, "TELNYX_FROM_NUMBER", "")
            ),
            "detail": "Required before setup-code texts, resident notices, and staff copies can be sent.",
            "url": "group_resident_message",
            "button": "Open Messaging",
        },
        {
            "label": "Resident app links",
            "complete": bool(settings.APP_STORE_URL or settings.GOOGLE_PLAY_URL),
            "detail": "Add App Store and Google Play URLs when the mobile apps are published.",
            "url": "property_owner_dashboard",
            "button": "Owner Dashboard",
        },
        {
            "label": "Demo link",
            "complete": bool(settings.DEMO_PUBLIC_URL),
            "detail": "Public demo URL lets prospects try the system without touching production data.",
            "url": "rental_ledger_demo",
            "button": "Open Demo",
        },
    ]

    return render(request, "owner_onboarding_wizard.html", {
        "properties": properties,
        "property_steps": property_steps,
        "portfolio_completed_steps": portfolio_completed_steps,
        "portfolio_total_steps": portfolio_total_steps,
        "portfolio_percent_complete": int(portfolio_completed_steps / portfolio_total_steps * 100) if portfolio_total_steps else 0,
        "launch_steps": launch_steps,
        "launch_completed_steps": sum(1 for step in launch_steps if step["complete"]),
        "launch_total_steps": len(launch_steps),
    })


def owner_properties_for(user):
    if is_super_admin(user) or is_assistant_admin(user):
        return Property.objects.all().order_by("name")

    return Property.objects.filter(owner_email__iexact=user.email).order_by("name")


@login_required
@user_passes_test(can_access_owner_dashboard)
def owner_payment_settings(request):
    properties = owner_properties_for(request.user)
    owner_email = request.user.email
    if request.method == "POST":
        config_id = request.POST.get("config_id")
        instance = None
        if config_id:
            instance = get_object_or_404(StripePaymentConfiguration, id=config_id)
            if not is_super_admin(request.user) and not is_assistant_admin(request.user):
                allowed_property_ids = set(properties.values_list("id", flat=True))
                if instance.property_id and instance.property_id not in allowed_property_ids:
                    messages.error(request, "You cannot edit payment settings for that property.")
                    return redirect("owner_payment_settings")
                if not instance.property_id and instance.owner_email.lower() != owner_email.lower():
                    messages.error(request, "You cannot edit payment settings for that owner.")
                    return redirect("owner_payment_settings")

        form = StripePaymentConfigurationForm(request.POST, instance=instance, properties=properties, owner_email=owner_email)
        if form.is_valid():
            config = form.save(commit=False)
            if not is_super_admin(request.user) and not is_assistant_admin(request.user):
                config.owner_email = owner_email
            if config.property and not config.owner_email:
                config.owner_email = config.property.owner_email
            if not config.pk:
                existing_config = None
                if config.property:
                    existing_config = getattr(config.property, "stripe_payment_configuration", None)
                elif config.owner_email:
                    existing_config = (
                        StripePaymentConfiguration.objects
                        .filter(property__isnull=True, owner_email__iexact=config.owner_email)
                        .order_by("-updated_at")
                        .first()
                    )
                if existing_config:
                    existing_config.owner_email = config.owner_email
                    existing_config.account_mode = config.account_mode
                    existing_config.status = config.status
                    existing_config.stripe_account_id = config.stripe_account_id
                    existing_config.display_name = config.display_name
                    existing_config.notes = config.notes
                    existing_config.save()
                    messages.success(request, "Stripe payment settings updated.")
                    return redirect("owner_payment_settings")
            config.save()
            messages.success(request, "Stripe payment settings saved.")
            return redirect("owner_payment_settings")
    else:
        form = StripePaymentConfigurationForm(properties=properties, owner_email=owner_email)

    configs = (
        StripePaymentConfiguration.objects
        .filter(Q(property__in=properties) | Q(property__isnull=True, owner_email__iexact=owner_email))
        .select_related("property")
        .order_by("property__name", "-updated_at")
    )
    property_rows = [
        {
            "property": property_obj,
            "payment_setup": payment_setup_summary(property_obj),
        }
        for property_obj in properties
    ]

    return render(request, "owner_payment_settings.html", {
        "form": form,
        "configs": configs,
        "property_rows": property_rows,
        "platform_stripe_ready": bool(settings.STRIPE_PUBLIC_KEY and settings.STRIPE_SECRET_KEY),
    })


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
