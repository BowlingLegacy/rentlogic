from django.contrib import messages
from django.contrib.auth import authenticate, login
from django.shortcuts import redirect, render

from .models import Property


def dashboard_for_user(user):
    if user.is_superuser or getattr(user, "role", "") == "admin":
        return "superadmin_dashboard"

    if getattr(user, "role", "") == "property_owner":
        return "property_owner_dashboard"

    if user.email and Property.objects.filter(owner_email__iexact=user.email).exists():
        return "property_owner_dashboard"

    if user.is_staff or getattr(user, "role", "") in ["landlord", "assistant"]:
        return "landlord_dashboard"

    return "tenant_dashboard"


def role_login(request):
    if request.user.is_authenticated:
        return redirect(dashboard_for_user(request.user))

    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)
            return redirect(dashboard_for_user(user))

        messages.error(request, "Invalid username or password.")

    return render(request, "login.html")
