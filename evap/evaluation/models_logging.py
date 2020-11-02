from collections import defaultdict, namedtuple
from datetime import date, datetime, time
from enum import Enum
import itertools
import threading
from json import JSONEncoder

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.contrib.postgres.fields import JSONField
from django.db import models
from django.db.models.signals import m2m_changed
from django.dispatch import receiver
from django.forms.models import model_to_dict
from django.template.defaultfilters import yesno
from django.utils.formats import localize
from django.utils.translation import gettext_lazy as _


class FieldActionType(str, Enum):
    M2M_ADD = "add"
    M2M_REMOVE = "remove"
    M2M_CLEAR = "clear"
    INSTANCE_CREATE = "create"
    VALUE_CHANGE = "change"
    INSTANCE_DELETE = "delete"


FieldAction = namedtuple("FieldAction", "label type items")


class InstanceActionType(str, Enum):
    CREATE = "create"
    CHANGE = "change"
    DELETE = "delete"


class LogJSONEncoder(JSONEncoder):
    """
    As JSON can't store datetime objects, we localize them to strings.
    """

    def default(self, o):
        # o is the object to serialize -- we can't rename the argument in JSONEncoder
        if isinstance(o, (date, time, datetime)):
            return localize(o)
        return super().default(o)


def _choice_to_display(field, choice):  # does not support nested choices
    for key, label in field.choices:
        if key == choice:
            return label
    return choice


def _field_actions_for_field(field, actions):
    label = getattr(field, "verbose_name", field.name).capitalize()

    for field_action_type, items in actions.items():
        if field.many_to_many or field.many_to_one or field.one_to_one:
            # convert item values from primary keys to string-representation for relation-based fields
            related_objects = field.related_model.objects.filter(pk__in=items)
            missing = len(items) - related_objects.count()
            items = [str(obj) for obj in related_objects] + [_("<deleted object>")] * missing
        elif hasattr(field, "choices") and field.choices:
            # convert values from choice-based fields to their display equivalent
            items = [_choice_to_display(field, item) for item in items]
        elif isinstance(field, models.BooleanField):
            # convert boolean to yes/no
            items = list(map(yesno, items))
        yield FieldAction(label, field_action_type, items)


class LogEntry(models.Model):
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, related_name="logs_about_me")
    content_object_id = models.PositiveIntegerField(db_index=True)
    content_object = GenericForeignKey("content_type", "content_object_id")
    attached_to_object_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, related_name="logs_for_me")
    attached_to_object_id = models.PositiveIntegerField(db_index=True)
    attached_to_object = GenericForeignKey("attached_to_object_type", "attached_to_object_id")
    datetime = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT)
    action_type = models.CharField(max_length=255, choices=[(value, value) for value in InstanceActionType])
    request_id = models.CharField(max_length=36, null=True, blank=True)
    data = JSONField(default=dict, encoder=LogJSONEncoder)

    class Meta:
        ordering = ("-datetime", "-id")

    @property
    def field_context_data(self):
        model = self.content_type.model_class()
        return {
            field_name: list(_field_actions_for_field(model._meta.get_field(field_name), actions))
            for field_name, actions in self.data.items()
        }

    @property
    def message(self):
        if self.action_type == InstanceActionType.CHANGE:
            if self.content_object:
                message = _("The {cls} {obj} was changed.")
            else:  # content_object might be deleted
                message = _("A {cls} was changed.")
        elif self.action_type == InstanceActionType.CREATE:
            if self.content_object:
                message = _("The {cls} {obj} was created.")
            else:
                message = _("A {cls} was created.")
        elif self.action_type == InstanceActionType.DELETE:
            message = _("A {cls} was deleted.")

        return message.format(
            cls=self.content_type.model_class()._meta.verbose_name_raw,
            obj=f'"{str(self.content_object)}"' if self.content_object else "",
        )


class LoggedModel(models.Model):
    thread = threading.local()

    class Meta:
        abstract = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._logentry = None

    def _as_dict(self):
        """
        Return a dict mapping field names to values saved in this instance.
        Only include field names that are not to be ignored for logging and
        that don't name m2m fields.
        """
        fields = [
            field.name for field in type(self)._meta.get_fields() if
            field.name not in self.unlogged_fields
            and not field.many_to_many
        ]
        return model_to_dict(self, fields)

    def _get_change_data(self, action_type: InstanceActionType):
        """
        Return a dict mapping field names to changes that happened in this model instance,
        depending on the action that is being done to the instance.
        """
        self_dict = self._as_dict()
        if action_type == InstanceActionType.CREATE:
            changes = {
                field_name: {FieldActionType.INSTANCE_CREATE: [created_value]}
                for field_name, created_value in self_dict.items()
                if created_value is not None
            }
        elif action_type == InstanceActionType.CHANGE:
            old_dict = type(self).objects.get(pk=self.pk)._as_dict()
            changes = {
                field_name: {FieldActionType.VALUE_CHANGE: [old_value, self_dict[field_name]]}
                for field_name, old_value in old_dict.items()
                if old_value != self_dict[field_name]
            }
        elif action_type == InstanceActionType.DELETE:
            old_dict = type(self).objects.get(pk=self.pk)._as_dict()
            changes = {
                field_name: {FieldActionType.INSTANCE_DELETE: [deleted_value]}
                for field_name, deleted_value in old_dict.items()
                if deleted_value is not None
            }
            # as the instance is being deleted, we also need to pull out all m2m values
            m2m_field_names = [field.name for field in type(self)._meta.many_to_many if field.name not in self.unlogged_fields]
            for field_name, related_objects in model_to_dict(self, m2m_field_names).items():
                changes[field_name] = {FieldActionType.INSTANCE_DELETE: [obj.pk for obj in related_objects]}
        else:
            raise ValueError("Unknown action type: '{}'".format(action_type))

        return changes

    def log_m2m_change(self, changes):
        self._update_log(changes, InstanceActionType.CHANGE)

    def log_instance_create(self):
        changes = self._get_change_data(InstanceActionType.CREATE)
        self._update_log(changes, InstanceActionType.CREATE)

    def log_instance_change(self):
        changes = self._get_change_data(InstanceActionType.CHANGE)
        self._update_log(changes, InstanceActionType.CHANGE)

    def log_instance_delete(self):
        changes = self._get_change_data(InstanceActionType.DELETE)
        self._update_log(changes, InstanceActionType.DELETE)

    def _update_log(self, changes, action_type: InstanceActionType):
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
                action_type=action_type,
                data=changes,
            )
        else:
            self._logentry.data.update(changes)

        self._logentry.save()

    def save(self, *args, **kw):
        # Are we creating a new instance?
        # https://docs.djangoproject.com/en/3.0/ref/models/instances/#customizing-model-loading
        if self._state.adding:
            # we need to attach a logentry to an existing object, so we save this newly created instance first
            super().save(*args, **kw)
            self.log_instance_create()
        else:
            # when saving an existing instance, we get changes by comparing to the version from the database
            # therefore we save the instance after building the logentry
            self.log_instance_change()
            super().save(*args, **kw)

    def delete(self, *args, **kw):
        self.log_instance_delete()
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
        yield from (list(group) for key, group in itertools.groupby(
            self.related_logentries().select_related("user"),
            lambda entry: entry.request_id or entry.pk,
        ))

    @property
    def object_to_attach_logentries_to(self):
        """
        Return a model class and primary key for the object for which this logentry should be shown.
        By default, show it to the object described by the logentry itself.

        Returning the model instance directly might rely on fetching that object from the database,
        which can break bulk loading in some cases, so we don't do that.
        """
        return type(self), self.pk

    @property
    def unlogged_fields(self):
        """Specify a list of field names so that these fields don't get logged."""
        return ['id', 'order']


@receiver(m2m_changed)
def _m2m_changed(sender, instance, action, reverse, model, pk_set, **kwargs):  # pylint: disable=unused-argument
    if reverse:
        return
    if not isinstance(instance, LoggedModel):
        return

    field_name = next((field.name for field in type(instance)._meta.many_to_many
                       if getattr(type(instance), field.name).through == sender), None)

    if field_name in instance.unlogged_fields:
        return

    m2m_changes = defaultdict(lambda: defaultdict(list))
    if action == 'pre_remove':
        m2m_changes[field_name][FieldActionType.M2M_REMOVE] += list(pk_set)
    elif action == 'pre_add':
        m2m_changes[field_name][FieldActionType.M2M_ADD] += list(pk_set)
    elif action == 'pre_clear':
        m2m_changes[field_name][FieldActionType.M2M_CLEAR] = []

    if m2m_changes:
        instance.log_m2m_change(m2m_changes)
