from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q, Sum
from django.dispatch import Signal
from django.utils.translation import gettext_lazy as _

from evap.evaluation.models import Semester, UserProfile
from evap.evaluation.tools import translate


class RewardPointRedemptionEvent(models.Model):
    name_de = models.CharField(max_length=1024, unique=True, verbose_name=_("name (german)"))
    name_en = models.CharField(max_length=1024, unique=True, verbose_name=_("name (english)"))
    name = translate(en="name_en", de="name_de")
    date = models.DateField(verbose_name=_("event date"))
    redeem_end_date = models.DateField(verbose_name=_("redemption end date"))
    # Note that we allow this value to change throughout the lifetime of the event.
    step = models.PositiveSmallIntegerField(
        verbose_name=_("redemption step"), help_text=_("Only multiples of this step can be redeemed."), default=1
    )

    @property
    def can_delete(self):
        return not self.reward_point_redemptions.exists()

    def users_with_redeemed_points(self):
        return UserProfile.objects.filter(reward_point_redemptions__event=self).annotate(
            points=Sum("reward_point_redemptions__value", default=0, filter=Q(reward_point_redemptions__event=self))
        )


class RewardPointGranting(models.Model):
    """
    Handles reward point amounts. As reward points might be connected to monetary transactions,
    instances may not be altered or deleted after creation.
    """

    user_profile = models.ForeignKey(UserProfile, models.CASCADE, related_name="reward_point_grantings")
    semester = models.ForeignKey(Semester, models.PROTECT, related_name="reward_point_grantings")
    granting_time = models.DateTimeField(verbose_name=_("granting time"), auto_now_add=True)
    value = models.IntegerField(verbose_name=_("value"), validators=[MinValueValidator(1)])

    granted_by_participation_removal = Signal()
    granted_by_evaluation_deletion = Signal()


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
