from collections import defaultdict, namedtuple
from datetime import date, datetime, time, timedelta
from enum import Enum, auto
import itertools
import logging
import operator
import secrets
import threading
import uuid
from json import JSONEncoder

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, Group, PermissionsMixin
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.contrib.postgres.fields import ArrayField, JSONField
from django.core.cache import caches
from django.core.exceptions import FieldDoesNotExist, ValidationError
from django.core.mail import EmailMessage
from django.db import IntegrityError, models, transaction
from django.db.models import Count, Manager, Q
from django.db.models.signals import m2m_changed
from django.dispatch import Signal, receiver
from django.forms import model_to_dict
from django.forms.models import model_to_dict
from django.template import Context, Template
from django.template.base import TemplateSyntaxError
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import localize
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from django_fsm import FSMField, transition
from django_fsm.signals import post_transition
from evap.evaluation.tools import clean_email, date_to_datetime, is_external_email, translate

logger = logging.getLogger(__name__)
FieldAction = namedtuple("FieldAction", "label type items")


class LogJSONEncoder(JSONEncoder):

    def default(self, obj):
        if obj is None:
            return ""
        if isinstance(obj, (date, time, datetime)):
            return localize(obj)
        return super().default(self, obj)


class LogEntry(models.Model):
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, related_name="logs_about_me")
    content_object_id = models.PositiveIntegerField(db_index=True)
    content_object = GenericForeignKey("content_type", "content_object_id")
    attached_to_object_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, related_name="logs_for_me")
    attached_to_object_id = models.PositiveIntegerField(db_index=True)
    attached_to_object = GenericForeignKey("attached_to_object_type", "attached_to_object_id")
    datetime = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT)
    action_type = models.CharField(max_length=255)
    request_id = models.CharField(max_length=36, null=True, blank=True)
    data = JSONField(default=dict, encoder=LogJSONEncoder)

    class Meta:
        ordering = ("-datetime", "-id")

    @staticmethod
    def _pk_to_string_representation(key, field, related_objects):
        if key is None:
            return key
        try:
            return str(related_objects.get(pk=key))
        except field.related_model.DoesNotExist:
            return "�"

    def _evaluation_log_template_context(self, data):
        fields = defaultdict(list)
        model = self.content_type.model_class()

        def choice_to_display(field, choice):  # does not support nested choices
            return next(filter(lambda t: t[0] == choice, field.choices), (choice, choice))[1]

        for field_name, actions in data.items():
            field = model._meta.get_field(field_name)
            try:
                label = getattr(field, "verbose_name", field_name).capitalize()
            except FieldDoesNotExist:
                label = field_name.capitalize()

            if field.many_to_many or field.many_to_one or field.one_to_one:
                # Convert item values from primary keys to string-representation for special fields
                related_ids = itertools.chain(*actions.values())
                related_objects = field.related_model.objects.filter(pk__in=related_ids)
                bool(related_objects)  # force queryset evaluation
                for field_action_type, primary_keys in actions.items():
                    items = [self._pk_to_string_representation(key, field, related_objects) for key in primary_keys]
                    fields[field_name].append(FieldAction(label, field_action_type, items))
            elif hasattr(field, "choices") and field.choices:
                for field_action_type, items in actions.items():
                    fields[field_name].append(FieldAction(
                        label, field_action_type, [choice_to_display(field, item) for item in items])
                    )
            else:
                for field_action_type, items in actions.items():
                    fields[field_name].append(FieldAction(label, field_action_type, items))
        return dict(fields)

    def display(self):
        if self.action_type not in ("change", "create", "delete"):
            raise ValueError("Unknown action type: '{}'!".format(self.action_type))

        if self.action_type == 'change':
            if self.content_object:
                message = _("The {cls} {obj} was changed.")
            else:
                message = _("A {cls} was changed.")
        elif self.action_type == 'create':
            if self.content_object:
                message = _("The {cls} {obj} was created.")
            else:
                message = _("A {cls} was created.")
        elif self.action_type == 'delete':
            message = _("A {cls} was deleted.")

        message = message.format(
            cls=self.content_type.model_class()._meta.verbose_name_raw,
            obj=f"\"{self.content_object!s}\"" if self.content_object else "",
        )

        return render_to_string("log/changed_fields_entry.html", {
            'message': message,
            'fields': self._evaluation_log_template_context(self.data),
        })


class LoggedModel(models.Model):
    thread = threading.local()

    class Meta:
        abstract = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._m2m_changes = defaultdict(lambda: defaultdict(list))
        self._logentry = None

    @receiver(m2m_changed)
    def _m2m_changed(sender, instance, action, reverse, model, pk_set, **kwargs):
        if reverse:
            return
        if not isinstance(instance, LoggedModel):
            return

        field_name = next((field.name for field in type(instance)._meta.many_to_many
                           if getattr(type(instance), field.name).through == sender), None)
        if field_name is None:
            return

        if action == 'pre_remove':
            instance._m2m_changes[field_name]['remove'] += list(pk_set)
        elif action == 'pre_add':
            instance._m2m_changes[field_name]['add'] += list(pk_set)
        elif action == 'pre_clear':
            instance._m2m_changes[field_name]['clear'] = []

        if "pre" in action:
            instance._update_log("m2m")

    def _as_dict(self, include_m2m=False):
        """
        Return a dict mapping field names to values saved in this instance.
        Only include field names that are not to be ignored for logging.
        Except when deleting objects, m2m values come from signal handling.
        """
        fields = [
            field.name for field in type(self)._meta.get_fields() if
            field.name not in self.unlogged_fields
            and (include_m2m or not field.many_to_many)
        ]
        return model_to_dict(self, fields)

    def _get_change_data(self, action_type, include_none_values=False):
        """
        Return a dict mapping field names to changes that happened in this model instance,
        depending on the action that is being done to the instance.
        """
        self_dict = self._as_dict()
        if action_type == "create":
            changes = {
                field_name: {'change': [None, created_value]}
                for field_name, created_value in self_dict.items()
                if created_value is not None or include_none_values
            }
        elif action_type == "change":
            old_dict = type(self).objects.get(pk=self.pk)._as_dict()
            changes = {
                field_name: {'change': [old_value, self_dict[field_name]]}
                for field_name, old_value in old_dict.items()
                if old_value != self_dict[field_name]
            }
        elif action_type == "delete":
            old_dict = type(self).objects.get(pk=self.pk)._as_dict(include_m2m=True)
            changes = {}
            for field_name, old_value in old_dict.items():
                if old_value is None and not include_none_values:
                    continue
                field = self._meta.get_field(field_name)
                if field.many_to_many:
                    action_items = [obj.pk for obj in old_value]
                else:
                    action_items = [old_value]
                changes[field_name] = {'delete': action_items}
        else:
            raise ValueError("Unknown action type: '{}'".format(action_type))

        changes.update(self._m2m_changes)
        return changes

    def _update_log(self, mode):
        action = {
            'delete': 'delete',
            'create': 'create',
            'change': 'change',
            'm2m': 'change',
        }[mode]

        changes = self._get_change_data(action)
        if not changes:
            return

        if not self._logentry:
            try:
                user = self.thread.request.user
                request_id = self.thread.request_id
            except AttributeError:
                user = None
                request_id = None
            attach_to_model, attached_to_object_id = self.object_to_attach_logentries_to
            attached_to_object_type = ContentType.objects.get_for_model(attach_to_model)
            self._logentry = LogEntry(
                content_object=self,
                attached_to_object_type=attached_to_object_type,
                attached_to_object_id=attached_to_object_id,
                user=user,
                request_id=request_id,
                action_type=action,
                data=changes,
            )
        else:
            self._logentry.data.update(changes)

        self._logentry.save()

    def save(self, *args, **kw):
        # Are we creating a new instance?
        # https://docs.djangoproject.com/en/3.0/ref/models/instances/#customizing-model-loading
        mode = "create" if self._state.adding else "change"
        if mode == "create":
            super().save(*args, **kw)

        self._update_log(mode)

        if mode == "change":
            super().save(*args, **kw)

    def delete(self, *args, **kw):
        self._update_log(mode="delete")
        self.related_logentries().delete()
        super().delete(*args, **kw)

    def related_logentries(self):
        """
        Return a queryset with all logentries that should be shown with this model.
        """
        return LogEntry.objects.filter(
            attached_to_object_type=ContentType.objects.get_for_model(type(self)), attached_to_object_id=self.pk,
        )

    def grouped_logentries(self):
        """
        Returns a list of lists of logentries for display. The order is not changed.
        Logentries are grouped if they have a matching request_id.
        """
        groups = []
        group = []
        for entry in self.related_logentries().select_related("user"):
            if not group:
                group.append(entry)
            elif entry.request_id is not None and group[0].request_id == entry.request_id:
                group.append(entry)
            else:
                time_matches = abs(group[0].datetime - entry.datetime) < timedelta(seconds=10)
                if entry.request_id is None and group[0].request_id is None and time_matches:
                    group.append(entry)
                else:
                    groups.append(group)
                    group = [entry]

        if group:
            groups.append(group)

        return groups

    @property
    def object_to_attach_logentries_to(self):
        """
        Return a model class and primary key for the object for which this logentry should be shown.
        By default, show it to the object described by the logentry itself.
        """
        return type(self), self.pk

    @property
    def unlogged_fields(self):
        """Specify a list of field names so that these fields don't get logged."""
        return ['id', 'last_modified_time', 'last_modified_user', 'order']
