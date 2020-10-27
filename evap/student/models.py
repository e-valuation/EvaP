from django.db import models
from django.contrib.postgres.fields import ArrayField
from django.utils.translation import gettext_lazy as _

from evap.evaluation.tools import translate


class TextAnswerWarning(models.Model):
    warning_text_de = models.CharField(max_length=1024, verbose_name=_("Warning text (German)"))
    warning_text_en = models.CharField(max_length=1024, verbose_name=_("Warning text (English)"))
    warning_text = translate(en='warning_text_en', de='warning_text_de')

    trigger_strings = ArrayField(models.CharField(max_length=1024), default=list,
        verbose_name=_("Trigger strings (case-insensitive)"), blank=True)

    order = models.IntegerField(verbose_name=_("Warning order"), default=-1)

    class Meta:
        ordering = ['order']
