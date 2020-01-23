from django import forms
from django.forms import ModelForm
from django.contrib.auth.models import User


class ProfileEditForm(ModelForm):
    class Meta:
        model = User
        fields = ['first_name']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control col-xl-5 col-md-6'})
        }
