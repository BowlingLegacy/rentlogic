from django.conf import settings


def demo_mode(request):
    return {
        "demo_mode": getattr(settings, "DEMO_MODE", False),
        "demo_session_seconds": getattr(settings, "DEMO_SESSION_SECONDS", 7200),
        "demo_public_url": getattr(settings, "DEMO_PUBLIC_URL", ""),
        "rental_ledger_site": getattr(settings, "RENTAL_LEDGER_SITE", False),
    }
