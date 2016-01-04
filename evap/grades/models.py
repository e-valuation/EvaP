from django.conf import settings
from django.db import models
from django.utils.translation import ugettext_lazy as _
from evap.evaluation.meta import LocalizeModelBase, Translate

import os

from evap.evaluation.models import Course

def helper_upload_path(instance, filename):
    return "grades/{}/{}".format(instance.course.id, filename)

class GradeDocument(models.Model, metaclass=LocalizeModelBase):
    course = models.ForeignKey(Course, models.PROTECT, related_name='grade_documents', verbose_name=_("Course"))
    file = models.FileField(upload_to=helper_upload_path, verbose_name=_("File")) #upload_to="grades/{}/".format(course.id),

    MIDTERM_GRADES = 'MID'
    FINAL_GRADES = 'FIN'
    GRADE_DOCUMENT_TYPES = (
        (MIDTERM_GRADES, _('midterm grades')),
        (FINAL_GRADES, _('final grades')),
    )
    type = models.CharField(max_length=3, choices=GRADE_DOCUMENT_TYPES, verbose_name=_('grade type'), default=MIDTERM_GRADES)

    description_de = models.CharField(max_length=255, verbose_name=_("description (german)"))
    description_en = models.CharField(max_length=255, verbose_name=_("description (english)"))

    description = Translate

    last_modified_time = models.DateTimeField(auto_now=True, verbose_name=_("Created"))
    last_modified_user = models.ForeignKey(settings.AUTH_USER_MODEL, models.SET_NULL, related_name="last_modified_user+", null=True, blank=True)

    class Meta:
        verbose_name = _("Grade Document")
        verbose_name_plural = _("Grade Documents")
        unique_together = (
            ('course', 'description_de'),
            ('course', 'description_en')
        )

    def __unicode__(self):
        return self.description

    def filename(self):
        return os.path.basename(self.file.name)
