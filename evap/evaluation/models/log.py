from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.dispatch import Signal
from django.core.serializers.json import DjangoJSONEncoder

from django.core.exceptions import FieldDoesNotExist
import datetime
from . import Course, Evaluation

from django.utils.formats import localize
from django.utils.translation import ugettext_lazy as _
import json
from django.template.loader import render_to_string

# logentry_display = Signal()
"""
To display an instance of the ``LogEntry`` model to a human user,
``evap.evaluation.models.logentry_display`` will be sent out with a ``logentry`` argument.
The first received response that is not ``None`` will be used to display the log entry
to the user. The receivers are expected to return plain text.
"""


class LogEntry(models.Model):
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField(db_index=True)
    content_object = GenericForeignKey("content_type", "object_id")
    datetime = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT)
    action_type = models.CharField(max_length=255)
    data = models.TextField(default="{}")

    class Meta:
        ordering = ("-datetime", "-id")

    def display(self):
        if self.action_type in ('evap.evaluation.changed', 'evap.evaluation.created'):
            fields = json.loads(self.data)
            for field_name in fields.keys():
                try:
                    model_field = self.content_type.model_class()._meta.get_field(field_name)
                    fields[field_name].append(getattr(model_field, "verbose_name", field_name))
                except FieldDoesNotExist:
                    fields[field_name].append(field_name)

            return render_to_string("log/changed_fields_entry.html", {
                'message': {'evap.evaluation.changed': _("The evaluation was changed."),
                            'evap.evaluation.created': _("The evaluation was created.")}[self.action_type],
                'fields': fields
            })

        if self.action_type == 'evap.evaluation.created':
            return _("The evaluation was created.")

        return self.action_type +": " + self.data


def log_serialize(obj):
    if obj is None:
        return ""
    if type(obj) in (datetime.date, datetime.time, datetime.datetime):
        return localize(obj)
    return str(obj)
