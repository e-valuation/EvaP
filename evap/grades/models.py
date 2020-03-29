import os

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.db.models.signals import pre_delete, pre_save
from django.dispatch.dispatcher import receiver

from evap.evaluation.models import Course
from evap.evaluation.tools import translate


def helper_upload_path(instance, filename):
    return "grades/{}/{}".format(instance.course.id, filename)


class GradeDocument(models.Model):
    course = models.ForeignKey(Course, models.PROTECT, related_name='grade_documents', verbose_name=_("course"))
    file = models.FileField(upload_to=helper_upload_path, verbose_name=_("File"))  # upload_to="grades/{}/".format(course.id),

    MIDTERM_GRADES = 'MID'
    FINAL_GRADES = 'FIN'
    GRADE_DOCUMENT_TYPES = (
        (MIDTERM_GRADES, _('midterm grades')),
        (FINAL_GRADES, _('final grades')),
    )
    type = models.CharField(max_length=3, choices=GRADE_DOCUMENT_TYPES, verbose_name=_('grade type'), default=MIDTERM_GRADES)

    description_de = models.CharField(max_length=255, verbose_name=_("description (german)"))
    description_en = models.CharField(max_length=255, verbose_name=_("description (english)"))
    description = translate(en='description_en', de='description_de')

    last_modified_time = models.DateTimeField(auto_now=True, verbose_name=_("Created"))
    last_modified_user = models.ForeignKey(settings.AUTH_USER_MODEL, models.SET_NULL, related_name="grades_last_modified_user+", null=True, blank=True)

    class Meta:
        verbose_name = _("Grade Document")
        verbose_name_plural = _("Grade Documents")
        unique_together = (
            ('course', 'description_de'),
            ('course', 'description_en')
        )

    def __str__(self):
        return self.description

    def filename(self):
        return os.path.basename(self.file.name)


@receiver(pre_delete, sender=GradeDocument)
def delete_file_pre_delete(instance, **_kwargs):
    if instance.file:
        instance.file.delete(False)


# Changing should lead to the removal of the old file
@receiver(pre_save, sender=GradeDocument)
def delete_file_pre_save(instance, **_kwargs):
    if not instance.pk:  # We do not want to trigger document creation
        return
    try:
        oldFile = GradeDocument.objects.get(pk=instance.pk).file
    except GradeDocument.DoesNotExist:
        return
    newFile = instance.file
    if not oldFile == newFile:
        oldFile.delete(False)
