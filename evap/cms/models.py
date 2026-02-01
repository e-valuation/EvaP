from django.db import models
from django.utils.translation import gettext_lazy as _

from evap.evaluation.models import Course, Evaluation
from evap.evaluation.tools import translate


class EvaluationLink(models.Model):
    evaluation = models.ForeignKey(
        Evaluation, models.CASCADE, verbose_name=_("evaluation"), related_name="evaluation_links"
    )

    # unique reference for import from campus management system
    cms_id = models.CharField(verbose_name=_("campus management system id"), unique=True, max_length=255)

    class Meta:
        verbose_name = _("evaluation link")
        verbose_name_plural = _("evaluation links")


class CourseLink(models.Model):
    course = models.ForeignKey(Course, models.CASCADE, verbose_name=_("course"), related_name="course_links")

    # unique reference for import from campus management system
    cms_id = models.CharField(verbose_name=_("campus management system id"), unique=True, max_length=255)

    class Meta:
        verbose_name = _("course link")
        verbose_name_plural = _("course links")


class IgnoredEvaluation(models.Model):
    """Model for an evaluation that was deleted and should not be imported again from the CMS"""

    # unique reference for import from campus management system
    cms_id = models.CharField(verbose_name=_("campus management system id"), unique=True, max_length=255)

    name_de = models.CharField(max_length=1024, verbose_name=_("name (german)"), blank=True)
    name_en = models.CharField(max_length=1024, verbose_name=_("name (english)"), blank=True)
    name = translate(en="name_en", de="name_de")

    course = models.ForeignKey(Course, models.CASCADE, verbose_name=_("course"), related_name="ignored_evaluations")

    notes = models.TextField(verbose_name=_("notes"), blank=True)

    class Meta:
        verbose_name = _("ignored evaluation")
        verbose_name_plural = _("ignored evaluations")

    def __str__(self):
        if self.name:
            return f"{self.course.name} – {self.name}"
        return self.course.name
