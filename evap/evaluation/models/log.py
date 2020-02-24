from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.dispatch import Signal
from django.core.serializers.json import DjangoJSONEncoder

from django.core.exceptions import FieldDoesNotExist
import datetime
from . import Course, Evaluation, Contribution

from django.utils.formats import localize
from django.utils.translation import ugettext_lazy as _
import json
from django.template.loader import render_to_string

from collections import defaultdict, namedtuple


FieldAction = namedtuple("FieldAction", "label type items")


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
        fields = defaultdict(list)
        for field_name, actions in data.items():
            for action_type, items in actions.items():
                try:
                    model = self.content_type.model_class()
                    field = model._meta.get_field(field_name)
                    label = getattr(field, "verbose_name", field_name)
                    if field.many_to_many or field.many_to_one or field.one_to_one:
                        related_objects = field.related_model.objects.filter(pk__in=items)
                        bool(related_objects)  # force queryset evaluation
                        items = [str(related_objects.get(pk=item)) if item is not None else "" for item in items]
                except FieldDoesNotExist:
                    label = field_name
                finally:
                    fields[field_name].append(FieldAction(label, action_type, items))
        return dict(fields)

    def display(self):
        message = None

        if self.action_type == 'changed':
            message = _("The {cls} {obj} was changed.")
        elif self.action_type == 'created':
            message = _("The {cls} {obj} was created.")

        if message: 
            field_data = json.loads(self.data)
            return render_to_string("log/changed_fields_entry.html", {
                'message': message.format(cls=str(type(self.content_object)), obj=str(self.content_object)),
                'fields': self._evaluation_log_template_context(field_data),
            })

        return self.action_type +": " + self.data


def log_serialize(obj):
    if obj is None:
        return ""
    if type(obj) in (datetime.date, datetime.time, datetime.datetime):
        return localize(obj)
    return str(obj)
