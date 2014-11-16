from django.utils.translation import ugettext_lazy as _
from django.db import models

from collections import defaultdict

from operator import attrgetter

class RewardPointRedemptionEvent(models.Model):
    name = models.CharField(max_length=1024, verbose_name=_(u"event name"))
    date = models.DateField(verbose_name=_(u"event date"))
    redeem_end_date = models.DateField(verbose_name=_(u"redemption end date"))

    @property
    def can_delete(self):
        if RewardPointRedemption.objects.filter(event=self).exists():
            return False
        return True
    
    def redemptions_by_user(self):
        redemptions = self.reward_point_redemptions.all()
        redemptions = sorted(redemptions, key=attrgetter('user_profile.user.last_name', 'user_profile.user.first_name'))
        redemptions_dict = defaultdict(list)
        for redemption in redemptions:
            redemptions_dict[redemption.user_profile].append(redemption)
        return redemptions_dict

class RewardPointGranting(models.Model):
    user_profile = models.ForeignKey('evaluation.UserProfile', related_name="reward_point_grantings")
    semester = models.ForeignKey('evaluation.Semester', related_name="reward_point_grantings", blank=True, null=True)
    granting_time = models.DateTimeField(verbose_name=_(u"granting time"), auto_now_add=True)
    value = models.IntegerField(verbose_name=_(u"value"), default=0)

class RewardPointRedemption(models.Model):
    user_profile = models.ForeignKey('evaluation.UserProfile', related_name="reward_point_redemptions")
    redemption_time = models.DateTimeField(verbose_name=_(u"redemption time"), auto_now_add=True)
    value = models.IntegerField(verbose_name=_(u"value"), default=0)
    event = models.ForeignKey(RewardPointRedemptionEvent, related_name="reward_point_redemptions")

class SemesterActivation(models.Model):
    semester = models.ForeignKey('evaluation.Semester', related_name='rewards_active', unique=True)
    is_active = models.BooleanField(default=False)
