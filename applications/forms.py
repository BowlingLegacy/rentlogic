from django import forms

from .models import HousingApplication


class LandlordCreateTenantForm(forms.Form):
    lease_start_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}),
    )
    monthly_rent = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        initial=0,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
    )
    balance = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        initial=0,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
    )
    rent_due_day = forms.IntegerField(
        initial=1,
        min_value=1,
        max_value=31,
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )
    deposit_required = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        initial=450,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
    )
    deposit_paid = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        initial=0,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
    )
    utility_monthly = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        initial=66,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
    )
    utility_balance = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        initial=0,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
    )
    space_type = forms.CharField(
        max_length=50,
        required=False,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "Room, Unit, Space, Suite",
        }),
    )
    space_label = forms.CharField(
        max_length=50,
        required=False,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "Example: A, 101, Suite 2",
        }),
    )
    additional_notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            "class": "form-control",
            "rows": 3,
            "placeholder": "Owner or property manager notes",
        }),
    )


class HousingApplicationForm(forms.ModelForm):
    class Meta:
        model = HousingApplication
        fields = [
            "property",
            "full_name",
            "phone",
            "email",
            "age",
            "current_address",
            "income_source",
            "monthly_income",
            "housing_need",
            "additional_notes",
        ]
        widgets = {
            "property": forms.Select(attrs={"class": "form-select"}),
            "full_name": forms.TextInput(attrs={"class": "form-control"}),
            "phone": forms.TextInput(attrs={"class": "form-control"}),
            "email": forms.EmailInput(attrs={"class": "form-control"}),
            "age": forms.NumberInput(attrs={"class": "form-control"}),
            "current_address": forms.TextInput(attrs={"class": "form-control"}),
            "income_source": forms.TextInput(attrs={"class": "form-control"}),
            "monthly_income": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "housing_need": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
            "additional_notes": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }
