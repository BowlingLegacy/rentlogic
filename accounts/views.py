from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required

from .models import InviteCode, Profile
from .forms import InviteCodeEntryForm, CodeSignupForm, CreateUserInviteForm


def enter_code(request):
    if request.method == "POST":
        form = InviteCodeEntryForm(request.POST)

        if form.is_valid():
            code_value = form.cleaned_data["code"].strip().upper()

            try:
                invite = InviteCode.objects.get(code=code_value, is_used=False)
            except InviteCode.DoesNotExist:
                messages.error(request, "Invalid or already-used invite code.")
                return render(request, "accounts/enter_code.html", {"form": form})

            request.session["invite_code_id"] = invite.id
            return redirect("signup")

    else:
        form = InviteCodeEntryForm()

    return render(request, "accounts/enter_code.html", {"form": form})


def signup(request):
    invite_id = request.session.get("invite_code_id")

    if not invite_id:
        messages.error(request, "Please enter a valid invite code first.")
        return redirect("enter_code")

    try:
        invite = InviteCode.objects.get(id=invite_id, is_used=False)
    except InviteCode.DoesNotExist:
        messages.error(request, "That invite code is no longer valid.")
        request.session.pop("invite_code_id", None)
        return redirect("enter_code")

    if request.method == "POST":
        form = CodeSignupForm(request.POST)

        if form.is_valid():
            user = form.save(commit=False)
            user.email = form.cleaned_data["email"]
            user.first_name = invite.full_name
            user.save()

            role = invite.role_to_create
            status = "applying" if role == "user" else "new"

            Profile.objects.create(
                user=user,
                role=role,
                status=status,
                phone=invite.phone
            )

            invite.is_used = True
            invite.save()

            login(request, user)
            request.session.pop("invite_code_id", None)

            if role == "owner":
                return redirect("owner_dashboard")

            return redirect("application_page")

    else:
        form = CodeSignupForm(initial={
            "email": invite.email,
            "phone": invite.phone,
        })

    return render(request, "accounts/signup.html", {
        "form": form,
        "invite": invite,
    })


def application_page(request):
    return render(request, "accounts/application.html")


@login_required
def owner_dashboard(request):
    form = CreateUserInviteForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        InviteCode.objects.create(
            full_name=form.cleaned_data["full_name"],
            email=form.cleaned_data["email"],
            phone=form.cleaned_data["phone"],
            role_to_create="user",
            created_by=request.user,
        )

        messages.success(request, "Renter invite code created and email sent.")
        return redirect("owner_dashboard")

    invites = InviteCode.objects.filter(created_by=request.user).order_by("-created_at")

    return render(request, "accounts/owner_dashboard.html", {
        "form": form,
        "invites": invites,
    })


@login_required
def user_dashboard(request):
    return render(request, "accounts/user_dashboard.html")