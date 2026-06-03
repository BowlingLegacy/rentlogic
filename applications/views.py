from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import get_object_or_404, redirect, render

from accounts.models import InviteCode, Profile

from .forms import HousingApplicationForm, LandlordCreateTenantForm
from .models import HousingApplication


def owner_or_staff_required(user):
    if user.is_staff or user.is_superuser:
        return True

    return Profile.objects.filter(user=user, role="owner").exists()


@login_required
def application_page(request):
    if request.method == "POST":
        form = HousingApplicationForm(request.POST, request.FILES)

        if form.is_valid():
            application = form.save(commit=False)
            application.applicant_user = request.user
            application.status = "submitted"
            application.save()

            messages.success(request, "Application submitted.")
            return redirect("user_dashboard")
    else:
        form = HousingApplicationForm(initial={"email": request.user.email})

    return render(request, "applications/application.html", {"form": form})


@login_required
@user_passes_test(owner_or_staff_required)
def create_tenant(request):
    application = get_object_or_404(
        HousingApplication,
        id=request.GET.get("application"),
    )

    if request.method == "POST":
        form = LandlordCreateTenantForm(request.POST)

        if form.is_valid():
            application.space_type = form.cleaned_data.get("space_type", "")
            application.space_label = form.cleaned_data.get("space_label", "")
            application.monthly_rent = form.cleaned_data.get("monthly_rent") or 0
            application.balance = form.cleaned_data.get("balance") or 0
            application.rent_due_day = form.cleaned_data.get("rent_due_day") or 1
            application.lease_start_date = form.cleaned_data.get("lease_start_date")
            application.deposit_required = form.cleaned_data.get("deposit_required") or 0
            application.deposit_paid = form.cleaned_data.get("deposit_paid") or 0
            application.utility_monthly = form.cleaned_data.get("utility_monthly") or 0
            application.utility_balance = form.cleaned_data.get("utility_balance") or 0
            application.additional_notes = form.cleaned_data.get("additional_notes") or ""
            application.status = "onboarding"

            if not application.onboarding_invite:
                invite = InviteCode.objects.create(
                    full_name=application.full_name,
                    email=application.email,
                    phone=application.phone,
                    role_to_create="user",
                    created_by=request.user,
                )
                application.onboarding_invite = invite

            application.save()

            messages.success(
                request,
                "Application approved and resident onboarding invite created.",
            )

            return render(request, "applications/landlord_create_tenant_success.html", {
                "application": application,
                "invite": application.onboarding_invite,
            })

    else:
        form = LandlordCreateTenantForm(initial={
            "monthly_rent": application.monthly_rent,
            "balance": application.balance,
            "deposit_required": application.deposit_required,
            "deposit_paid": application.deposit_paid,
            "utility_monthly": application.utility_monthly,
            "utility_balance": application.utility_balance,
            "space_type": application.space_type,
            "space_label": application.space_label,
            "rent_due_day": application.rent_due_day,
            "lease_start_date": application.lease_start_date,
        })

    return render(request, "applications/landlord_create_tenant.html", {
        "form": form,
        "application": application,
    })
