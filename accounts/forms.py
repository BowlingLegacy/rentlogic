from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm


class InviteCodeEntryForm(forms.Form):
    code = forms.CharField(label="Invite Code", max_length=50)


class CodeSignupForm(UserCreationForm):
    email = forms.EmailField(required=True)
    phone = forms.CharField(required=False, max_length=20)

    class Meta:
        model = User
        fields = ["username", "email", "phone", "password1", "password2"]


class CreateUserInviteForm(forms.Form):
    full_name = forms.CharField(label="Renter / Applicant Name", max_length=100)
    email = forms.EmailField(label="Email Address")
    phone = forms.CharField(label="Phone Number", max_length=20)