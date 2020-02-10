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

from collections import defaultdict


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
            field_data = json.loads(self.data)
            field_meta = defaultdict(dict)
            for field_name in field_data.keys():
                try:
                    model = self.content_type.model_class()
                    model_field = model._meta.get_field(field_name)
                    field_meta[field_name]['label'] = getattr(model_field, "verbose_name", field_name)
                    if model_field.many_to_many:
                        field_meta[field_name]['type'] = 'm2m'
                        for m2m_action in field_data[field_name]:
                            if m2m_action not in 'add remove':
                                continue
                            field_data[field_name][m2m_action] = [str(obj) for obj in
                            model_field.related_model.objects.filter(pk__in=field_data[field_name][m2m_action])]

                except FieldDoesNotExist:
                    field_meta[field_name]['label'] = field_name
                    field_meta[field_name]['type'] = 'default'

            return render_to_string("log/changed_fields_entry.html", {
                'message': {'evap.evaluation.changed': _("The evaluation was changed."),
                            'evap.evaluation.created': _("The evaluation was created.")}[self.action_type],
                'fields': zip(field_meta.values(), field_data.values()),
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
