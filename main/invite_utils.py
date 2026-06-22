from django.conf import settings
from django.core.mail import send_mail
from django.utils.text import slugify

from .models import User


def create_pending_portal_user(full_name, email, role, source_id):
    base_username = slugify(full_name) or role.replace("_", "-")
    username = f"{base_username}-{source_id}-{role.replace('_', '-')}"
    original_username = username
    counter = 1

    while User.objects.filter(username=username).exists():
        counter += 1
        username = f"{original_username}-{counter}"

    return User.objects.create_user(
        username=username,
        email=email,
        password=None,
        role=role,
        is_staff=role in ["landlord", "assistant"],
        is_superuser=False,
    )


def send_portal_access_invite_email(user, full_name, role_label):
    if not user or not user.email:
        return False

    if not user.invite_code or user.invite_code_used_at:
        user.refresh_invite_code()

    send_mail(
        f"Your RentalReadyPro {role_label} Portal Access Code",
        f"""Hello {full_name or role_label},

Your RentalReadyPro {role_label.lower()} portal access code is:

{user.invite_code}

Portal setup:
https://rentalreadypro.com/enter-invite-code/

This code is single-use and expires 30 minutes after it is issued. If it expires, request a new code from the invite-code page.
If this email is not in your inbox, check your junk or spam folder.

Thank you,
RentalReadyPro
""",
        getattr(settings, "DEFAULT_FROM_EMAIL", None),
        [user.email],
        fail_silently=False,
    )

    return True

