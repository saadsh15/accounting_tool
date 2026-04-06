from django.contrib.auth.forms import UserCreationForm
from django import forms
from .models import User, Organization

class CustomUserCreationForm(UserCreationForm):
    organization_name = forms.CharField(
        max_length=255, 
        required=True, 
        help_text='Name of your company or organization.'
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = UserCreationForm.Meta.fields + ('email',)

    def save(self, commit=True):
        user = super().save(commit=False)
        org_name = self.cleaned_data.get('organization_name')
        if commit:
            # Create an organization for the new user
            org = Organization.objects.create(name=org_name)
            user.organization = org
            user.save()
        return user
