from pathlib import PurePosixPath

from django.conf import settings
from django.http import Http404
from django.db.models import Q
from django.views.static import serve

from .models import (
    AccountingReceipt,
    ApplicantDocument,
    BlogPost,
    ExistingResidentIntake,
    FinancialUpload,
    HousingApplication,
    Property,
    PropertyImage,
    PropertyOnboardingDocument,
    RentalListingPhoto,
)


def _managed_property_ids(user):
    if not user.is_authenticated:
        return Property.objects.none().values_list("id", flat=True)
    if user.is_superuser or getattr(user, "role", "") in ["admin", "assistant"]:
        return Property.objects.all().values_list("id", flat=True)
    if getattr(user, "role", "") == "property_owner":
        if settings.PROPERTY_MEMBERSHIP_ENFORCEMENT:
            return Property.objects.filter(memberships__user=user, memberships__role="owner").values_list("id", flat=True)
        return Property.objects.filter(Q(memberships__user=user, memberships__role="owner") | Q(owner_email__iexact=user.email)).distinct().values_list("id", flat=True)
    if getattr(user, "role", "") == "landlord":
        if settings.PROPERTY_MEMBERSHIP_ENFORCEMENT:
            return Property.objects.filter(memberships__user=user, memberships__role="manager").values_list("id", flat=True)
        return Property.objects.filter(Q(memberships__user=user, memberships__role="manager") | Q(landlord_email__iexact=user.email)).distinct().values_list("id", flat=True)
    return Property.objects.none().values_list("id", flat=True)


def secure_media(request, path):
    path = str(PurePosixPath(path))
    if path.startswith("../") or path.startswith("/"):
        raise Http404

    if path.startswith("blog_images/") and BlogPost.objects.filter(image=path).exists():
        return serve(request, path, document_root=settings.MEDIA_ROOT)
    if path.startswith("rental_listing_photos/") and RentalListingPhoto.objects.filter(image=path, listing__status="published").exists():
        return serve(request, path, document_root=settings.MEDIA_ROOT)
    if (
        (path.startswith("property_photos/") and Property.objects.filter(photo=path, rental_listings__status="published").exists())
        or (path.startswith("property_gallery/") and PropertyImage.objects.filter(image=path, property__rental_listings__status="published").exists())
    ):
        return serve(request, path, document_root=settings.MEDIA_ROOT)

    if not request.user.is_authenticated:
        raise Http404
    property_ids = _managed_property_ids(request.user)
    own_applications = HousingApplication.objects.filter(user=request.user)
    managed_applications = HousingApplication.objects.filter(property_id__in=property_ids)
    applications = own_applications | managed_applications

    authorized = (
        ApplicantDocument.objects.filter(file=path, application__in=applications).exists()
        or HousingApplication.objects.filter(id_upload=path).filter(id__in=applications).exists()
        or HousingApplication.objects.filter(background_report=path).filter(id__in=applications).exists()
        or HousingApplication.objects.filter(profile_photo=path).filter(id__in=applications).exists()
        or ExistingResidentIntake.objects.filter(profile_photo=path, application__in=applications).exists()
        or PropertyOnboardingDocument.objects.filter(source_file=path, property_id__in=property_ids).exists()
        or FinancialUpload.objects.filter(file=path, property_id__in=property_ids).exists()
        or AccountingReceipt.objects.filter(receipt_file=path, property_id__in=property_ids).exists()
        or Property.objects.filter(photo=path, id__in=property_ids).exists()
        or PropertyImage.objects.filter(image=path, property_id__in=property_ids).exists()
        or RentalListingPhoto.objects.filter(image=path, listing__property_id__in=property_ids).exists()
    )
    if not authorized:
        raise Http404
    return serve(request, path, document_root=settings.MEDIA_ROOT)
