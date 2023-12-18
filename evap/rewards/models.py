from collections import OrderedDict

from django.core.validators import MinValueValidator
from django.db import models
from django.dispatch import Signal
from django.utils.translation import gettext_lazy as _

from evap.evaluation.models import Semester, UserProfile


class NoPointsSelectedError(Exception):
    """An attempt has been made to redeem <= 0 points."""


class NotEnoughPointsError(Exception):
    """An attempt has been made to redeem more points than available."""


class OutdatedRedemptionDataError(Exception):
    """A redemption request has been sent with outdated data, e.g. when a request has been sent twice."""


class RedemptionEventExpiredError(Exception):
    """An attempt has been made to redeem more points for an event whose redeem_end_date lies in the past."""


class RewardPointRedemptionEvent(models.Model):
    name = models.CharField(max_length=1024, verbose_name=_("event name"))
    date = models.DateField(verbose_name=_("event date"))
    redeem_end_date = models.DateField(verbose_name=_("redemption end date"))

    @property
    def can_delete(self):
        return not self.reward_point_redemptions.exists()

    def redemptions_by_user(self):
        redemptions = self.reward_point_redemptions.order_by("user_profile").prefetch_related("user_profile")
        redemptions_dict = OrderedDict()
        for redemption in redemptions:
            if redemption.user_profile not in redemptions_dict:
                redemptions_dict[redemption.user_profile] = 0
            redemptions_dict[redemption.user_profile] += redemption.value
        return redemptions_dict


class RewardPointGranting(models.Model):
    """
    Handles reward point amounts. As reward points might be connected to monetary transactions,
    instances may not be altered or deleted after creation.
    """

    user_profile = models.ForeignKey(UserProfile, models.CASCADE, related_name="reward_point_grantings")
    semester = models.ForeignKey(Semester, models.PROTECT, related_name="reward_point_grantings")
    granting_time = models.DateTimeField(verbose_name=_("granting time"), auto_now_add=True)
    value = models.IntegerField(verbose_name=_("value"), validators=[MinValueValidator(1)])

    granted_by_removal = Signal()


class RewardPointRedemption(models.Model):
    """
    Handles reward point amounts. As reward points might be connected to monetary transactions,
    instances may not be altered or deleted after creation.
    """

    user_profile = models.ForeignKey(UserProfile, models.CASCADE, related_name="reward_point_redemptions")
    redemption_time = models.DateTimeField(verbose_name=_("redemption time"), auto_now_add=True)
    value = models.IntegerField(verbose_name=_("value"), validators=[MinValueValidator(1)])
    event = models.ForeignKey(RewardPointRedemptionEvent, models.PROTECT, related_name="reward_point_redemptions")


class SemesterActivation(models.Model):
    semester = models.OneToOneField(Semester, models.CASCADE, related_name="rewards_active")
    is_active = models.BooleanField(default=False)
