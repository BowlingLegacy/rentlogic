from django.db import models
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.conf import settings
import random
import string


# 🔐 Code generator
def generate_code(length):
    characters = string.ascii_uppercase + string.digits
    return "".join(random.choice(characters) for _ in range(length))


# 👤 Profile (role + status system)
class Profile(models.Model):
    ROLE_CHOICES = [
        ("admin", "Admin"),
        ("owner", "Owner"),
        ("user", "User"),
    ]

    STATUS_CHOICES = [
        ("new", "New"),
        ("applying", "Applying"),
        ("submitted", "Application Submitted"),
        ("approved", "Approved"),
        ("active", "Active Tenant"),
        ("denied", "Denied"),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="user")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="new")
    phone = models.CharField(max_length=20, blank=True)

    class Meta:
        verbose_name = "User Profile"
        verbose_name_plural = "User Profiles"

    def __str__(self):
        return f"{self.user.username} - {self.role} - {self.status}"


# 🎟 Invite Code system (AUTO-GENERATE + EMAIL)
class InviteCode(models.Model):
    ROLE_CHOICES = [
        ("owner", "Owner"),
        ("user", "User"),
    ]

    full_name = models.CharField(max_length=100)
    email = models.EmailField()
    phone = models.CharField(max_length=20)

    code = models.CharField(max_length=8, unique=True, blank=True)
    role_to_create = models.CharField(max_length=10, choices=ROLE_CHOICES)

    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    is_used = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Invite Code"
        verbose_name_plural = "Invite Codes (Access Control)"

    def save(self, *args, **kwargs):
        is_new = self.pk is None

        # Generate code automatically
        if not self.code:
            length = 8 if self.role_to_create == "owner" else 6
            self.code = generate_code(length)

        super().save(*args, **kwargs)

        # Send email ONLY on first creation
        if is_new:
            send_mail(
    subject="Welcome to RentLogic – Your Invitation",
    message=(
        f"Hello {self.full_name},\n\n"

        f"You’ve been invited to join RentLogic.\n\n"

        f"We’re excited to have you get started. This system will guide you through "
        f"your setup or application step-by-step.\n\n"

        f"Your secure invite code is:\n\n"
        f"{self.code}\n\n"

        f"Click the link below to begin:\n"
        f"http://127.0.0.1:8000/enter-code/\n\n"

        f"If you have any questions, contact the representative who requested your code.\n\n"

        f"— RentLogic Team"
    ),
    from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@rentlogic.com'),
    recipient_list=[self.email],
    fail_silently=True,
)

    def __str__(self):
        return f"{self.full_name} - {self.code}"