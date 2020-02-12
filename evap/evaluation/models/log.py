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

from collections import defaultdict, namedtuple


LOG_ACTION_TYPES = {
    'add': _("added"),
    'remove': _("removed"),
    'clear': _("cleared"),
    'change': _("changed"),
}


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

    def _evaluation_log_template_context(self, data):
        FieldAction = namedtuple("FieldAction", "label type items")
        fields = defaultdict(list)
        print(data)
        for field_name, actions in data.items():
            for action_type, items in actions.items():
                try:
                    model = self.content_type.model_class()
                    model_field = model._meta.get_field(field_name)
                    label = getattr(model_field, "verbose_name", field_name)
                    if model_field.many_to_many:
                        if action_type not in 'add remove':
                            continue
                        items = [str(obj) for obj in model_field.related_model.objects.filter(pk__in=items)]
                except FieldDoesNotExist:
                    label = field_name
                finally:
                    fields[field_name].append(FieldAction(label, action_type, items))
        print("result:", dict(fields))
        return dict(fields)

    def display(self):
        if self.action_type in ('evap.evaluation.changed', 'evap.evaluation.created'):
            field_data = json.loads(self.data)
            return render_to_string("log/changed_fields_entry.html", {
                'message': _("The evaluation was changed."),
                'fields': self._evaluation_log_template_context(field_data),
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
