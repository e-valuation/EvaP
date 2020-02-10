import operator
import random
from datetime import date, timedelta

from django.conf import settings
from django.contrib.auth.models import (AbstractBaseUser, BaseUserManager,
                                        Group, PermissionsMixin)
from django.contrib.contenttypes.models import ContentType
from django.db import IntegrityError, models
from django.urls import reverse
from django.utils.functional import cached_property
from django.utils.translation import ugettext_lazy as _
from django.forms.models import model_to_dict

from evap.evaluation.tools import (clean_email, date_to_datetime,
                                   is_external_email, translate)
from django.db.models.signals import m2m_changed
import json

from collections import defaultdict

class LoggedModel(models.Model):
    class Meta:
        abstract = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._initial = self._dict
        self._m2m_diff = defaultdict(lambda: defaultdict(list))
        self._logentry = None
        
        for field in type(self)._meta.many_to_many:
            self.register_logged_m2m_field(field)

    def register_logged_m2m_field(self, field):
        through = getattr(type(self), field.name).through  # converting from field to its descriptor
        m2m_changed.connect(
                LoggedModel.m2m_changed,
                sender=through,
                dispatch_uid="m2m_log-{!r}-{!r}".format(type(self), field)
        )

    @staticmethod
    def m2m_changed(sender, instance, action, reverse, model, pk_set, **kwargs):
        if reverse:
            return

        # import pdb
        # pdb.set_trace()

        field_name = next((field.name for field in type(instance)._meta.many_to_many
                                     if getattr(type(instance), field.name).through == sender), None)

        if action == 'pre_remove':
            instance._m2m_diff[field_name]['remove'] += list(pk_set)
        elif action == 'pre_add':
            instance._m2m_diff[field_name]['add'] += list(pk_set)
        elif action == 'pre_clear':
            instance._m2m_diff[field_name]['cleared'] = None

        if "pre" in action:
            instance.update_log()

        print(f"changed {field_name} by f{pk_set}")

    @property
    def _dict(self):
        return model_to_dict(self)

    @property
    def diff(self):
        d1 = self._initial
        d2 = self._dict
        changes = [(k, (v, d2[k])) for k, v in d1.items() if v != d2[k]]
        diff = dict(changes)
        diff.update(self._m2m_diff)
        return diff

    def update_log(self, user=None):
        from .log import log_serialize, LogEntry
        data = json.dumps(self.diff, default=log_serialize)
        if not self._logentry:
            action = 'evap.evaluation.changed' if 'id' in self._initial and self._initial['id'] else 'evap.evaluation.created'
            self._logentry = LogEntry(content_object=self, user=user, action_type=action, data=data)
        else:
            self._logentry.data = data
        self._logentry.save()

    def save(self, *args, **kw):
        super().save(*args, **kw)

        request = kw.get('request', getattr(self, '_request', None))
        if 'request' in kw:
            del kw['request']
        user = request and request.user or None
        self.update_log(user=user)

    def all_logentries(self):
        from .log import LogEntry
        return LogEntry.objects.filter(
            content_type=ContentType.objects.get_for_model(type(self)), object_id=self.pk,
        ).select_related("user")


class UserProfileManager(BaseUserManager):
    def create_user(self, username, email=None, password=None, first_name=None, last_name=None):
        if not username:
            raise ValueError(_("Users must have a username"))

        user = self.model(
            username=username, email=self.normalize_email(email), first_name=first_name, last_name=last_name,
        )
        user.set_password(password)
        user.save()
        return user

    def create_superuser(self, username, password, email=None, first_name=None, last_name=None):
        user = self.create_user(
            username=username,
            password=password,
            email=self.normalize_email(email),
            first_name=first_name,
            last_name=last_name,
        )
        user.is_superuser = True
        user.save()
        user.groups.add(Group.objects.get(name="Manager"))
        return user


class UserProfile(AbstractBaseUser, PermissionsMixin):
    username = models.CharField(max_length=255, unique=True, verbose_name=_("username"))

    # null=True because certain external users don't have an address
    email = models.EmailField(max_length=255, unique=True, blank=True, null=True, verbose_name=_("email address"),)

    title = models.CharField(max_length=255, blank=True, null=True, verbose_name=_("Title"))
    first_name = models.CharField(max_length=255, blank=True, null=True, verbose_name=_("first name"))
    last_name = models.CharField(max_length=255, blank=True, null=True, verbose_name=_("last name"))

    language = models.CharField(max_length=8, blank=True, null=True, verbose_name=_("language"))

    # delegates of the user, which can also manage their evaluations
    delegates = models.ManyToManyField(
        "UserProfile", verbose_name=_("Delegates"), related_name="represented_users", blank=True,
    )

    # users to which all emails should be sent in cc without giving them delegate rights
    cc_users = models.ManyToManyField(
        "UserProfile", verbose_name=_("CC Users"), related_name="ccing_users", blank=True,
    )

    # flag for proxy users which represent a group of users
    is_proxy_user = models.BooleanField(default=False, verbose_name=_("Proxy user"))

    # key for url based login of this user
    MAX_LOGIN_KEY = 2 ** 31 - 1

    login_key = models.IntegerField(verbose_name=_("Login Key"), unique=True, blank=True, null=True)
    login_key_valid_until = models.DateField(verbose_name=_("Login Key Validity"), blank=True, null=True)

    is_active = models.BooleanField(default=True, verbose_name=_("active"))

    class Meta:
        ordering = ("last_name", "first_name", "username")
        verbose_name = _("user")
        verbose_name_plural = _("users")

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = []

    objects = UserProfileManager()

    def save(self, *args, **kwargs):
        self.email = clean_email(self.email)
        super().save(*args, **kwargs)

    @property
    def full_name(self):
        if self.last_name:
            name = self.last_name
            if self.first_name:
                name = self.first_name + " " + name
            if self.title:
                name = self.title + " " + name
            return name

        return self.username.replace(" ", "\u00A0")  # replace spaces with non-breaking spaces

    @property
    def full_name_with_username(self):
        name = self.full_name
        if self.username not in name:
            name += " (" + self.username + ")"
        return name

    def __str__(self):
        return self.full_name

    @cached_property
    def is_staff(self):
        return self.is_manager or self.is_reviewer

    @cached_property
    def is_manager(self):
        return self.groups.filter(name="Manager").exists()

    @cached_property
    def is_reviewer(self):
        return self.is_manager or self.groups.filter(name="Reviewer").exists()

    @cached_property
    def is_grade_publisher(self):
        return self.groups.filter(name="Grade publisher").exists()

    @property
    def can_be_marked_inactive_by_manager(self):
        if self.is_reviewer or self.is_grade_publisher or self.is_superuser:
            return False
        if any(not evaluation.participations_are_archived for evaluation in self.evaluations_participating_in.all()):
            return False
        if any(not contribution.evaluation.participations_are_archived for contribution in self.contributions.all()):
            return False
        if self.is_proxy_user:
            return False
        return True

    @property
    def can_be_deleted_by_manager(self):
        if self.is_responsible or self.is_contributor or self.is_reviewer or self.is_grade_publisher or self.is_superuser:
            return False
        if any(not evaluation.participations_are_archived for evaluation in self.evaluations_participating_in.all()):
            return False
        if any(not user.can_be_deleted_by_manager for user in self.represented_users.all()):
            return False
        if any(not user.can_be_deleted_by_manager for user in self.ccing_users.all()):
            return False
        if self.is_proxy_user:
            return False
        return True

    @property
    def is_participant(self):
        return self.evaluations_participating_in.exists()

    @property
    def is_student(self):
        """
            A UserProfile is not considered to be a student anymore if the
            newest contribution is newer than the newest participation.
        """
        from . import Semester

        if not self.is_participant:
            return False

        if not self.is_contributor or self.is_responsible:
            return True

        last_semester_participated = (
            Semester.objects.filter(courses__evaluations__participants=self).order_by("-created_at").first()
        )
        last_semester_contributed = (
            Semester.objects.filter(courses__evaluations__contributions__contributor=self)
            .order_by("-created_at")
            .first()
        )

        return last_semester_participated.created_at >= last_semester_contributed.created_at

    @property
    def is_contributor(self):
        return self.contributions.exists()

    @property
    def is_editor(self):
        return self.contributions.filter(can_edit=True).exists() or self.is_responsible

    @property
    def is_responsible(self):
        return self.courses_responsible_for.exists()

    @property
    def is_delegate(self):
        return self.represented_users.exists()

    @property
    def is_editor_or_delegate(self):
        return self.is_editor or self.is_delegate

    @cached_property
    def is_responsible_or_contributor_or_delegate(self):
        return self.is_responsible or self.is_contributor or self.is_delegate

    @property
    def is_external(self):
        if not self.email:
            return True
        return is_external_email(self.email)

    @property
    def can_download_grades(self):
        return not self.is_external

    @staticmethod
    def email_needs_login_key(email):
        return is_external_email(email)

    @property
    def needs_login_key(self):
        return UserProfile.email_needs_login_key(self.email)

    def ensure_valid_login_key(self):
        if self.login_key and self.login_key_valid_until > date.today():
            self.reset_login_key_validity()
            return

        while True:
            key = random.randrange(0, UserProfile.MAX_LOGIN_KEY)
            try:
                self.login_key = key
                self.reset_login_key_validity()
                break
            except IntegrityError:
                # unique constraint failed, the login key was already in use. Generate another one.
                continue

    def reset_login_key_validity(self):
        self.login_key_valid_until = date.today() + timedelta(settings.LOGIN_KEY_VALIDITY)
        self.save()

    @property
    def login_url(self):
        if not self.needs_login_key:
            return ""
        return settings.PAGE_URL + reverse("evaluation:login_key_authentication", args=[self.login_key])

    def get_sorted_courses_responsible_for(self):
        return self.courses_responsible_for.order_by("semester__created_at", "name_de")

    def get_sorted_contributions(self):
        return self.contributions.order_by("evaluation__course__semester__created_at", "evaluation__name_de")

    def get_sorted_evaluations_participating_in(self):
        return self.evaluations_participating_in.order_by("course__semester__created_at", "name_de")

    def get_sorted_evaluations_voted_for(self):
        return self.evaluations_voted_for.order_by("course__semester__created_at", "name_de")

    def get_sorted_due_evaluations(self):
        due_evaluations = dict()
        from . import Evaluation
        for evaluation in Evaluation.objects.filter(participants=self, state="in_evaluation").exclude(voters=self):
            due_evaluations[evaluation] = (evaluation.vote_end_date - date.today()).days

        # Sort evaluations by number of days left for evaluation and bring them to following format:
        # [(evaluation, due_in_days), ...]
        return sorted(due_evaluations.items(), key=operator.itemgetter(1))
