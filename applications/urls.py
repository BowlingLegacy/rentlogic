from django.urls import path

from . import views


urlpatterns = [
    path("apply/", views.application_page, name="application_page"),
    path("create-tenant/", views.create_tenant, name="create_tenant"),
]
