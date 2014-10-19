from django.utils.translation import ugettext_lazy as _
from django.db import models

class RewardPointRedemptionEvent(models.Model):
	name = models.CharField(max_length=1024, verbose_name=_(u"event"))
	date = models.DateField(verbose_name=_(u"date"))
	redeem_end_date = models.DateField(verbose_name=_(u"date"))

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
