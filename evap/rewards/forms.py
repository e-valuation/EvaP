from django import forms

from evap.evaluation.forms import BootstrapMixin
from evap.rewards.models import RewardPointRedemptionEvent


class RewardPointRedemptionEventForm(forms.ModelForm, BootstrapMixin):
    class Meta:
        model = RewardPointRedemptionEvent
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['date'].localize = True
        self.fields['redeem_end_date'].localize = True
