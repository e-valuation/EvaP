from django import forms

from evap.rewards.models import RewardPointRedemptionEvent


class RewardPointRedemptionEventForm(forms.ModelForm):
    class Meta:
        model = RewardPointRedemptionEvent
        fields = ('name', 'date', 'redeem_end_date')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['date'].localize = True
        self.fields['redeem_end_date'].localize = True
