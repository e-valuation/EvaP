from django import forms
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User
from django.forms.fields import FileField
from django.forms.models import BaseInlineFormSet
from django.utils.translation import ugettext_lazy as _
from django.utils.text import normalize_newlines

from evap.evaluation.forms import BootstrapMixin
from evap.rewards.models import RewardPointRedemptionEvent


class RewardPointRedemptionEventForm(forms.ModelForm, BootstrapMixin):
    class Meta:
        model = RewardPointRedemptionEvent
        fields = "__all__"
