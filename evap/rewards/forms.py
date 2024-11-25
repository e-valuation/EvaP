from contextlib import contextmanager
from datetime import date

from django import forms
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.translation import gettext as _

from evap.evaluation.models import UserProfile
from evap.rewards.models import RewardPointRedemption, RewardPointRedemptionEvent
from evap.rewards.tools import reward_points_of_user


class RewardPointRedemptionEventForm(forms.ModelForm):
    class Meta:
        model = RewardPointRedemptionEvent
        fields = ("name", "date", "redeem_end_date", "step")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["date"].localize = True
        self.fields["redeem_end_date"].localize = True


class RewardPointRedemptionForm(forms.Form):
    event = forms.ModelChoiceField(queryset=RewardPointRedemptionEvent.objects.all(), widget=forms.HiddenInput())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.initial:
            return

        help_text = _("multiples of {}").format(self.initial["event"].step) if self.initial["event"].step > 1 else ""
        self.fields["points"] = forms.IntegerField(
            min_value=0,
            max_value=self.initial["total_points_available"],
            step_size=self.initial["event"].step,
            label="",
            help_text=help_text,
        )

    def clean_event(self):
        event = self.cleaned_data["event"]
        if event.redeem_end_date < date.today():
            raise ValidationError(_("Sorry, the deadline for this event expired already."))
        return event


class BaseRewardPointRedemptionFormSet(forms.BaseFormSet):
    def __init__(self, *args, user: UserProfile, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.user = user
        self.locked = False

    def get_form_kwargs(self, index):
        kwargs = super().get_form_kwargs(index)
        if not self.initial:
            return kwargs
        kwargs["initial"] = self.initial[index]
        kwargs["initial"]["total_points_available"] = reward_points_of_user(self.user)
        return kwargs

    @contextmanager
    def lock(self):
        with transaction.atomic():
            # lock these rows to prevent race conditions
            list(self.user.reward_point_grantings.select_for_update())
            list(self.user.reward_point_redemptions.select_for_update())

            self.locked = True
            try:
                yield
            finally:
                self.locked = False

    def clean(self):
        assert self.locked

        if any(self.errors):
            return

        total_points_available = reward_points_of_user(self.user)
        total_points_redeemed = sum(form.cleaned_data["points"] for form in self.forms)
        assert all(form.cleaned_data["points"] >= 0 for form in self.forms)

        if total_points_redeemed <= 0:
            raise ValidationError(_("You cannot redeem 0 points."))

        if total_points_redeemed > total_points_available:
            raise ValidationError(_("You don't have enough reward points."))

    def save(self) -> list[RewardPointRedemption]:
        assert self.locked

        created = []
        for form in self.forms:
            points = form.cleaned_data["points"]
            if not points:
                continue
            redemption = RewardPointRedemption.objects.create(
                user_profile=self.user, value=points, event=form.cleaned_data["event"]
            )
            created.append(redemption)
        return created


RewardPointRedemptionFormSet = forms.formset_factory(
    RewardPointRedemptionForm, formset=BaseRewardPointRedemptionFormSet, extra=0
)
