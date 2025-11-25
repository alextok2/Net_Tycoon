from django import forms
from .models import PlayerProfile

class CharacterForm(forms.ModelForm):
    class Meta:
        model = PlayerProfile
        fields = ['company_name', 'skin_color', 'hair_style', 'hair_color', 'shirt_color']