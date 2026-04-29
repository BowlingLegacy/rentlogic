from django.urls import path
from . import views

urlpatterns = [
    path("enter-code/", views.enter_code, name="enter_code"),
    path("signup/", views.signup, name="signup"),
    path("application/", views.application_page, name="application_page"),
    path("owner-dashboard/", views.owner_dashboard, name="owner_dashboard"),
    path("user-dashboard/", views.user_dashboard, name="user_dashboard"),
]