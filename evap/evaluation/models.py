from collections import defaultdict, namedtuple
from datetime import date, datetime, timedelta
from enum import Enum, auto
import logging
import operator
import secrets
import uuid

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, Group, PermissionsMixin
from django.contrib.postgres.fields import ArrayField
from django.core.cache import caches
from django.core.exceptions import ValidationError
from django.core.mail import EmailMessage
from django.db import IntegrityError, models, transaction
from django.db.models import Count, Manager, Q
from django.dispatch import Signal, receiver
from django.template import Context, Template
from django.template.base import TemplateSyntaxError
from django.urls import reverse
from django.utils import timezone
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from django_fsm import FSMField, transition
from django_fsm.signals import post_transition

from evap.evaluation.models_logging import LoggedModel
from evap.evaluation.tools import clean_email, date_to_datetime, is_external_email, translate

logger = logging.getLogger(__name__)


class NotArchiveable(Exception):
    """An attempt has been made to archive something that is not archiveable."""


class Semester(models.Model):
    """Represents a semester, e.g. the winter term of 2011/2012."""

    name_de = models.CharField(max_length=1024, unique=True, verbose_name=_("name (german)"))
    name_en = models.CharField(max_length=1024, unique=True, verbose_name=_("name (english)"))
    name = translate(en='name_en', de='name_de')

    short_name_de = models.CharField(max_length=20, unique=True, verbose_name=_("short name (german)"))
    short_name_en = models.CharField(max_length=20, unique=True, verbose_name=_("short name (english)"))
    short_name = translate(en='short_name_en', de='short_name_de')

    participations_are_archived = models.BooleanField(default=False, verbose_name=_("participations are archived"))
    grade_documents_are_deleted = models.BooleanField(default=False, verbose_name=_("grade documents are deleted"))
    results_are_archived = models.BooleanField(default=False, verbose_name=_("results are archived"))

    created_at = models.DateField(verbose_name=_("created at"), auto_now_add=True)

    is_active = models.BooleanField(default=None, unique=True, blank=True, null=True, verbose_name=_("semester is active"))

    class Meta:
        ordering = ('-created_at', 'pk')
        verbose_name = _("semester")
        verbose_name_plural = _("semesters")

    def __str__(self):
        return self.name

    @property
    def can_be_deleted_by_manager(self):
        if self.is_active:
            return False

        if self.evaluations.count() == 0:
            return True

        return self.participations_are_archived and self.grade_documents_are_deleted and self.results_are_archived

    @property
    def participations_can_be_archived(self):
        return not self.participations_are_archived and all(evaluation.participations_can_be_archived for evaluation in self.evaluations.all())

    @property
    def grade_documents_can_be_deleted(self):
        return not self.grade_documents_are_deleted

    @property
    def results_can_be_archived(self):
        return not self.results_are_archived

    @transaction.atomic
    def archive(self):
        if not self.participations_can_be_archived:
            raise NotArchiveable()
        for evaluation in self.evaluations.all():
            evaluation._archive()
        self.participations_are_archived = True
        self.save()

    @transaction.atomic
    def delete_grade_documents(self):
        # Resolving this circular dependency makes the code more ugly, so we leave it.
        # pylint: disable=import-outside-toplevel
        from evap.grades.models import GradeDocument

        if not self.grade_documents_can_be_deleted:
            raise NotArchiveable()
        GradeDocument.objects.filter(course__semester=self).delete()
        self.grade_documents_are_deleted = True
        self.save()

    def archive_results(self):
        if not self.results_can_be_archived:
            raise NotArchiveable()
        self.results_are_archived = True
        self.save()

    @classmethod
    def get_all_with_unarchived_results(cls):
        return cls.objects.filter(results_are_archived=False).distinct()

    @classmethod
    def get_all_with_published_unarchived_results(cls):
        return cls.objects.filter(courses__evaluations__state="published", results_are_archived=False).distinct()

    @classmethod
    def active_semester(cls):
        return cls.objects.filter(is_active=True).first()

    @property
    def evaluations(self):
        return Evaluation.objects.filter(course__semester=self)


class QuestionnaireManager(Manager):
    def general_questionnaires(self):
        return super().get_queryset().exclude(type=Questionnaire.Type.CONTRIBUTOR)

    def contributor_questionnaires(self):
        return super().get_queryset().filter(type=Questionnaire.Type.CONTRIBUTOR)


class Questionnaire(models.Model):
    """A named collection of questions."""

    class Type(models.IntegerChoices):
        TOP = 10, _('Top questionnaire')
        CONTRIBUTOR = 20, _('Contributor questionnaire')
        BOTTOM = 30, _('Bottom questionnaire')

    type = models.IntegerField(choices=Type.choices, verbose_name=_('type'), default=Type.TOP)

    name_de = models.CharField(max_length=1024, unique=True, verbose_name=_("name (german)"))
    name_en = models.CharField(max_length=1024, unique=True, verbose_name=_("name (english)"))
    name = translate(en='name_en', de='name_de')

    description_de = models.TextField(verbose_name=_("description (german)"), blank=True, null=True)
    description_en = models.TextField(verbose_name=_("description (english)"), blank=True, null=True)
    description = translate(en='description_en', de='description_de')

    public_name_de = models.CharField(max_length=1024, verbose_name=_("display name (german)"))
    public_name_en = models.CharField(max_length=1024, verbose_name=_("display name (english)"))
    public_name = translate(en='public_name_en', de='public_name_de')

    teaser_de = models.TextField(verbose_name=_("teaser (german)"), blank=True, null=True)
    teaser_en = models.TextField(verbose_name=_("teaser (english)"), blank=True, null=True)
    teaser = translate(en='teaser_en', de='teaser_de')

    order = models.IntegerField(verbose_name=_("ordering index"), default=0)

    class Visibility(models.IntegerChoices):
        HIDDEN = 0, _("Don't show")
        MANAGERS = 1, _("Managers only")
        EDITORS = 2, _("Managers and editors")

    visibility = models.IntegerField(choices=Visibility.choices, verbose_name=_('visibility'), default=Visibility.MANAGERS)

    is_locked = models.BooleanField(verbose_name=_("is locked"), default=False)

    objects = QuestionnaireManager()

    def clean(self):
        if self.type == self.Type.CONTRIBUTOR and self.is_locked:
            raise ValidationError({'is_locked': _('Contributor questionnaires cannot be locked.')})

    class Meta:
        ordering = ('type', 'order', 'pk')
        verbose_name = _("questionnaire")
        verbose_name_plural = _("questionnaires")

    def __str__(self):
        return self.name

    def __lt__(self, other):
        return (self.type, self.order, self.pk) < (other.type, other.order, other.pk)

    def __gt__(self, other):
        return (self.type, self.order, self.pk) > (other.type, other.order, other.pk)

    @property
    def is_above_contributors(self):
        return self.type == self.Type.TOP

    @property
    def is_below_contributors(self):
        return self.type == self.Type.BOTTOM

    @property
    def can_be_edited_by_manager(self):
        return not self.contributions.exclude(evaluation__state='new').exists()

    @property
    def can_be_deleted_by_manager(self):
        return not self.contributions.exists()

    @property
    def text_questions(self):
        return [question for question in self.questions.all() if question.is_text_question]

    @property
    def rating_questions(self):
        return [question for question in self.questions.all() if question.is_rating_question]

    SINGLE_RESULT_QUESTIONNAIRE_NAME = "Single result"

    @classmethod
    def single_result_questionnaire(cls):
        return cls.objects.get(name_en=cls.SINGLE_RESULT_QUESTIONNAIRE_NAME)


class Degree(models.Model):
    name_de = models.CharField(max_length=1024, verbose_name=_("name (german)"), unique=True)
    name_en = models.CharField(max_length=1024, verbose_name=_("name (english)"), unique=True)
    name = translate(en='name_en', de='name_de')
    import_names = ArrayField(models.CharField(max_length=1024), default=list, verbose_name=_("import names"), blank=True)

    order = models.IntegerField(verbose_name=_("degree order"), default=-1)

    class Meta:
        ordering = ['order', ]

    def __str__(self):
        return self.name

    def can_be_deleted_by_manager(self):
        if self.pk is None:
            return True
        return not self.courses.all().exists()


class CourseType(models.Model):
    """Model for the type of a course, e.g. a lecture"""

    name_de = models.CharField(max_length=1024, verbose_name=_("name (german)"), unique=True)
    name_en = models.CharField(max_length=1024, verbose_name=_("name (english)"), unique=True)
    name = translate(en='name_en', de='name_de')
    import_names = ArrayField(models.CharField(max_length=1024), default=list, verbose_name=_("import names"), blank=True)

    order = models.IntegerField(verbose_name=_("course type order"), default=-1)

    class Meta:
        ordering = ['order', ]

    def __str__(self):
        return self.name

    def can_be_deleted_by_manager(self):
        if not self.pk:
            return True
        return not self.courses.all().exists()


class Course(LoggedModel):
    """Models a single course, e.g. the Math 101 course of 2002."""
    semester = models.ForeignKey(Semester, models.PROTECT, verbose_name=_("semester"), related_name="courses")

    name_de = models.CharField(max_length=1024, verbose_name=_("name (german)"))
    name_en = models.CharField(max_length=1024, verbose_name=_("name (english)"))
    name = translate(en='name_en', de='name_de')

    # type of course: lecture, seminar, project
    type = models.ForeignKey(CourseType, models.PROTECT, verbose_name=_("course type"), related_name="courses")

    # e.g. Bachelor, Master
    degrees = models.ManyToManyField(Degree, verbose_name=_("degrees"), related_name="courses")

    # defines whether results can only be seen by contributors and participants
    is_private = models.BooleanField(verbose_name=_("is private"), default=False)

    # persons responsible for the course; their names will be shown next to course, they can edit the course and see general text answers
    responsibles = models.ManyToManyField(settings.AUTH_USER_MODEL, verbose_name=_("responsibles"), related_name="courses_responsible_for")

    # grade publishers can set this to True, then the course will be handled as if final grades have already been uploaded
    gets_no_grade_documents = models.BooleanField(verbose_name=_("gets no grade documents"), default=False)

    # who last modified this course
    last_modified_time = models.DateTimeField(default=timezone.now, verbose_name=_("Last modified"))
    last_modified_user = models.ForeignKey(settings.AUTH_USER_MODEL, models.SET_NULL, null=True, blank=True, related_name="courses_last_modified+")

    class Meta:
        unique_together = (
            ('semester', 'name_de'),
            ('semester', 'name_en'),
        )
        verbose_name = _("course")
        verbose_name_plural = _("courses")

    def __str__(self):
        return self.name

    @property
    def unlogged_fields(self):
        return super().unlogged_fields + ["semester", "gets_no_grade_documents"]

    def set_last_modified(self, modifying_user):
        self.last_modified_user = modifying_user
        self.last_modified_time = timezone.now()
        logger.info('Course "{}" (id {}) was edited by user {}.'.format(self, self.id, modifying_user.email))

    @property
    def can_be_edited_by_manager(self):
        return not self.semester.participations_are_archived

    @property
    def can_be_deleted_by_manager(self):
        return not self.evaluations.exists()

    @property
    def final_grade_documents(self):
        # We think it's better to use the imported constant here instead of using some workaround
        # pylint: disable=import-outside-toplevel
        from evap.grades.models import GradeDocument
        return self.grade_documents.filter(type=GradeDocument.Type.FINAL_GRADES)

    @property
    def midterm_grade_documents(self):
        # We think it's better to use the imported constant here instead of using some workaround
        # pylint: disable=import-outside-toplevel
        from evap.grades.models import GradeDocument
        return self.grade_documents.filter(type=GradeDocument.Type.MIDTERM_GRADES)

    @cached_property
    def responsibles_names(self):
        return ", ".join([responsible.full_name for responsible in self.responsibles.all().order_by("last_name")])

    @property
    def has_external_responsible(self):
        return any(responsible.is_external for responsible in self.responsibles.all())

    @property
    def all_evaluations_finished(self):
        return not self.evaluations.exclude(state__in=['evaluated', 'reviewed', 'published']).exists()


class Evaluation(LoggedModel):
    """Models a single evaluation, e.g. the exam evaluation of the Math 101 course of 2002."""
    state = FSMField(default='new', protected=True)

    course = models.ForeignKey(Course, models.PROTECT, verbose_name=_("course"), related_name="evaluations")

    # names can be empty, e.g., when there is just one evaluation in a course
    name_de = models.CharField(max_length=1024, verbose_name=_("name (german)"), blank=True)
    name_en = models.CharField(max_length=1024, verbose_name=_("name (english)"), blank=True)
    name = translate(en='name_en', de='name_de')

    # defines how large the influence of this evaluation's grade is on the total grade of its course
    weight = models.PositiveSmallIntegerField(verbose_name=_("weight"), default=1)

    is_single_result = models.BooleanField(verbose_name=_("is single result"), default=False)

    # whether participants must vote to qualify for reward points
    is_rewarded = models.BooleanField(verbose_name=_("is rewarded"), default=True)

    # whether the evaluation does take place during the semester, stating that evaluation results will be published while the course is still running
    is_midterm_evaluation = models.BooleanField(verbose_name=_("is midterm evaluation"), default=False)

    # True, if the evaluation has at least two voters or if the first voter explicitly confirmed that given text answers
    # can be published even if no other person evaluates the evaluation
    can_publish_text_results = models.BooleanField(verbose_name=_("can publish text results"), default=False)

    # students that are allowed to vote, or their count after archiving
    participants = models.ManyToManyField(settings.AUTH_USER_MODEL, verbose_name=_("participants"), blank=True, related_name='evaluations_participating_in')
    _participant_count = models.IntegerField(verbose_name=_("participant count"), blank=True, null=True, default=None)

    # students that already voted, or their count after archiving
    voters = models.ManyToManyField(settings.AUTH_USER_MODEL, verbose_name=_("voters"), blank=True, related_name='evaluations_voted_for')
    _voter_count = models.IntegerField(verbose_name=_("voter count"), blank=True, null=True, default=None)

    # when the evaluation takes place
    vote_start_datetime = models.DateTimeField(verbose_name=_("start of evaluation"))
    vote_end_date = models.DateField(verbose_name=_("last day of evaluation"))

    # Disable to prevent editors from changing evaluation data
    allow_editors_to_edit = models.BooleanField(verbose_name=_("allow editors to edit"), default=True)

    # who last modified this evaluation
    last_modified_time = models.DateTimeField(default=timezone.now, verbose_name=_("Last modified"))
    last_modified_user = models.ForeignKey(settings.AUTH_USER_MODEL, models.SET_NULL, null=True, blank=True, related_name="evaluations_last_modified+")

    evaluation_evaluated = Signal(providing_args=['request', 'semester'])

    # whether to wait for grade uploading before publishing results
    wait_for_grade_upload_before_publishing = models.BooleanField(verbose_name=_("wait for grade upload before publishing"), default=True)

    class TextAnswerReviewState(Enum):
        do_not_call_in_templates = True
        NO_TEXTANSWERS = auto()
        REVIEW_NEEDED = auto()
        REVIEW_URGENT = auto()
        REVIEWED = auto()

    class Meta:
        unique_together = (
            ('course', 'name_de'),
            ('course', 'name_en'),
        )
        verbose_name = _("evaluation")
        verbose_name_plural = _("evaluations")

    def __str__(self):
        return self.full_name

    def save(self, *args, **kw):
        super().save(*args, **kw)

        # make sure there is a general contribution
        if not self.general_contribution:
            self.contributions.create(contributor=None)
            del self.general_contribution  # invalidate cached property

        assert self.vote_end_date >= self.vote_start_datetime.date()

        if hasattr(self, 'state_change'):
            # It's clear that results.models will need to reference evaluation.models' classes in ForeignKeys.
            # However, this method only makes sense as a method of Evaluation. Thus, we can't get rid of these imports
            # pylint: disable=import-outside-toplevel
            if self.state_change == "published":
                from evap.results.tools import collect_results
                from evap.results.views import update_template_cache_of_published_evaluations_in_course
                collect_results(self)
                update_template_cache_of_published_evaluations_in_course(self.course)
            elif self.state_change == "unpublished":
                from evap.results.tools import get_collect_results_cache_key
                from evap.results.views import delete_template_cache, update_template_cache_of_published_evaluations_in_course
                caches['results'].delete(get_collect_results_cache_key(self))
                delete_template_cache(self)
                update_template_cache_of_published_evaluations_in_course(self.course)

    def set_last_modified(self, modifying_user):
        self.last_modified_user = modifying_user
        self.last_modified_time = timezone.now()
        logger.info('Evaluation "{}" (id {}) was edited by user {}.'.format(self, self.id, modifying_user.email))

    @property
    def full_name(self):
        if self.name:
            return "{} – {}".format(self.course.name, self.name)
        return self.course.name

    @property
    def full_name_de(self):
        if self.name_de:
            return "{} – {}".format(self.course.name_de, self.name_de)
        return self.course.name_de

    @property
    def full_name_en(self):
        if self.name_en:
            return "{} – {}".format(self.course.name_en, self.name_en)
        return self.course.name_en

    @property
    def is_fully_reviewed(self):
        if not self.can_publish_text_results:
            return True
        return not self.unreviewed_textanswer_set.exists()

    @property
    def vote_end_datetime(self):
        # The evaluation ends at EVALUATION_END_OFFSET_HOURS:00 of the day AFTER self.vote_end_date.
        return date_to_datetime(self.vote_end_date) + timedelta(hours=24 + settings.EVALUATION_END_OFFSET_HOURS)

    @property
    def is_in_evaluation_period(self):
        return self.vote_start_datetime <= datetime.now() <= self.vote_end_datetime

    @property
    def general_contribution_has_questionnaires(self):
        return self.general_contribution and self.general_contribution.questionnaires.count() > 0

    @property
    def all_contributions_have_questionnaires(self):
        return self.general_contribution and not self.contributions.annotate(Count('questionnaires')).filter(questionnaires__count=0).exists()

    def can_be_voted_for_by(self, user):
        """Returns whether the user is allowed to vote on this evaluation."""
        return (self.state == "in_evaluation"
            and self.is_in_evaluation_period
            and user in self.participants.all()
            and user not in self.voters.all())

    def can_be_seen_by(self, user):
        if user.is_manager:
            return True
        if self.state == 'new':
            return False
        if user.is_reviewer and not self.course.semester.results_are_archived:
            return True
        if self.course.is_private or user.is_external:
            return self.is_user_responsible_or_contributor_or_delegate(user) or self.participants.filter(pk=user.pk).exists()
        return True

    def can_results_page_be_seen_by(self, user):
        if self.is_single_result:
            return False
        if user.is_manager:
            return True
        if user.is_reviewer and not self.course.semester.results_are_archived:
            return True
        if self.state != 'published':
            return False
        if not self.can_publish_rating_results or self.course.semester.results_are_archived:
            return self.is_user_responsible_or_contributor_or_delegate(user)
        return self.can_be_seen_by(user)

    @property
    def can_be_edited_by_manager(self):
        return not self.participations_are_archived and self.state in ['new', 'prepared', 'editor_approved', 'approved', 'in_evaluation', 'evaluated', 'reviewed']

    @property
    def can_be_deleted_by_manager(self):
        return self.can_be_edited_by_manager and (self.num_voters == 0 or self.is_single_result)

    @cached_property
    def num_participants(self):
        if self._participant_count is not None:
            return self._participant_count
        return self.participants.count()

    def _archive(self):
        """Should be called only via Semester.archive"""
        if not self.participations_can_be_archived:
            raise NotArchiveable()
        if self._participant_count is not None:
            assert self._voter_count is not None
            assert self.is_single_result or self._voter_count == self.voters.count() and self._participant_count == self.participants.count()
            return
        assert self._participant_count is None and self._voter_count is None
        self._participant_count = self.num_participants
        self._voter_count = self.num_voters
        self.save()
        self.related_logentries().delete()

    @property
    def participations_are_archived(self):
        semester_participations_are_archived = self.course.semester.participations_are_archived
        if semester_participations_are_archived:
            assert self._participant_count is not None and self._voter_count is not None
        return semester_participations_are_archived

    @property
    def participations_can_be_archived(self):
        return not self.course.semester.participations_are_archived and self.state in ["new", "published"]

    @property
    def has_external_participant(self):
        return any(participant.is_external for participant in self.participants.all())

    @property
    def can_publish_average_grade(self):
        if self.is_single_result:
            return True

        # the average grade is only published if at least the configured percentage of participants voted during the evaluation for significance reasons
        return self.can_publish_rating_results and self.num_voters / self.num_participants >= settings.VOTER_PERCENTAGE_NEEDED_FOR_PUBLISHING_AVERAGE_GRADE

    @property
    def can_publish_rating_results(self):
        if self.is_single_result:
            return True

        # the rating results are only published if at least the configured number of participants voted during the evaluation for anonymity reasons
        return self.num_voters >= settings.VOTER_COUNT_NEEDED_FOR_PUBLISHING_RATING_RESULTS

    @transition(field=state, source=['new', 'editor_approved'], target='prepared')
    def ready_for_editors(self):
        pass

    @transition(field=state, source='prepared', target='editor_approved')
    def editor_approve(self):
        pass

    @transition(field=state, source=['new', 'prepared', 'editor_approved'], target='approved', conditions=[lambda self: self.general_contribution_has_questionnaires])
    def manager_approve(self):
        pass

    @transition(field=state, source=['prepared', 'editor_approved', 'approved'], target='new')
    def revert_to_new(self):
        pass

    @transition(field=state, source='approved', target='in_evaluation', conditions=[lambda self: self.is_in_evaluation_period])
    def evaluation_begin(self):
        pass

    @transition(field=state, source=['evaluated', 'reviewed'], target='in_evaluation', conditions=[lambda self: self.is_in_evaluation_period])
    def reopen_evaluation(self):
        pass

    @transition(field=state, source='in_evaluation', target='evaluated')
    def evaluation_end(self):
        pass

    @transition(field=state, source='evaluated', target='reviewed', conditions=[lambda self: self.is_fully_reviewed])
    def review_finished(self):
        pass

    @transition(field=state, source=['new', 'reviewed'], target='reviewed', conditions=[lambda self: self.is_single_result])
    def single_result_created(self):
        pass

    @transition(field=state, source='reviewed', target='evaluated', conditions=[lambda self: not self.is_fully_reviewed])
    def reopen_review(self):
        pass

    @transition(field=state, source='reviewed', target='published')
    def publish(self):
        assert self.is_single_result or self._voter_count is None and self._participant_count is None
        self._voter_count = self.num_voters
        self._participant_count = self.num_participants

        if not self.can_publish_text_results:
            self.textanswer_set.delete()
        else:
            self.textanswer_set.filter(state=TextAnswer.State.HIDDEN).delete()
            self.textanswer_set.update(original_answer=None)

    @transition(field=state, source='published', target='reviewed')
    def unpublish(self):
        assert self.is_single_result or self._voter_count == self.voters.count() and self._participant_count == self.participants.count()
        self._voter_count = None
        self._participant_count = None

    @cached_property
    def general_contribution(self):
        try:
            return self.contributions.get(contributor=None)
        except Contribution.DoesNotExist:
            return None

    @cached_property
    def num_voters(self):
        if self._voter_count is not None:
            return self._voter_count
        return self.voters.count()

    @property
    def due_participants(self):
        return self.participants.exclude(pk__in=self.voters.all())

    @cached_property
    def num_contributors(self):
        return UserProfile.objects.filter(contributions__evaluation=self).count()

    @property
    def days_left_for_evaluation(self):
        return (self.vote_end_date - date.today()).days

    @property
    def time_left_for_evaluation(self):
        return self.vote_end_datetime - datetime.now()

    def evaluation_ends_soon(self):
        return 0 < self.time_left_for_evaluation.total_seconds() < settings.EVALUATION_END_WARNING_PERIOD * 3600

    @property
    def days_until_evaluation(self):
        days_left = (self.vote_start_datetime.date() - date.today()).days
        if self.vote_start_datetime < datetime.now():
            days_left -= 1
        return days_left

    def is_user_editor_or_delegate(self, user):
        represented_user_pks = [represented_user.pk for represented_user in user.represented_users.all()]
        represented_user_pks.append(user.pk)
        return self.contributions.filter(contributor__pk__in=represented_user_pks, role=Contribution.Role.EDITOR).exists() or self.course.responsibles.filter(pk__in=represented_user_pks).exists()

    def is_user_responsible_or_contributor_or_delegate(self, user):
        # early out that saves database hits since is_responsible_or_contributor_or_delegate is a cached_property
        if not user.is_responsible_or_contributor_or_delegate:
            return False
        represented_user_pks = [represented_user.pk for represented_user in user.represented_users.all()]
        represented_user_pks.append(user.pk)
        return self.contributions.filter(contributor__pk__in=represented_user_pks).exists() or self.course.responsibles.filter(pk__in=represented_user_pks).exists()

    def is_user_contributor(self, user):
        return self.contributions.filter(contributor=user).exists()

    @property
    def textanswer_set(self):
        return TextAnswer.objects.filter(contribution__evaluation=self)

    @cached_property
    def num_textanswers(self):
        if not self.can_publish_text_results:
            return 0
        return self.textanswer_set.count()

    @property
    def unreviewed_textanswer_set(self):
        return self.textanswer_set.filter(state=TextAnswer.State.NOT_REVIEWED)

    @property
    def reviewed_textanswer_set(self):
        return self.textanswer_set.exclude(state=TextAnswer.State.NOT_REVIEWED)

    @cached_property
    def num_reviewed_textanswers(self):
        return self.reviewed_textanswer_set.count()

    @property
    def textanswer_review_state(self):
        if self.num_textanswers == 0:
            return self.TextAnswerReviewState.NO_TEXTANSWERS

        if self.num_textanswers == self.num_reviewed_textanswers:
            return self.TextAnswerReviewState.REVIEWED

        if self.state != "evaluated":
            return self.TextAnswerReviewState.REVIEW_NEEDED

        if (self.course.final_grade_documents
                or self.course.gets_no_grade_documents
                or not self.wait_for_grade_upload_before_publishing):
            return self.TextAnswerReviewState.REVIEW_URGENT

        return self.TextAnswerReviewState.REVIEW_NEEDED

    @property
    def ratinganswer_counters(self):
        return RatingAnswerCounter.objects.filter(contribution__evaluation=self)

    @classmethod
    def update_evaluations(cls):
        logger.info("update_evaluations called. Processing evaluations now.")

        evaluations_new_in_evaluation = []
        evaluation_results_evaluations = []

        for evaluation in cls.objects.all():
            try:
                if evaluation.state == "approved" and evaluation.vote_start_datetime <= datetime.now():
                    evaluation.evaluation_begin()
                    evaluation.save()
                    evaluations_new_in_evaluation.append(evaluation)
                elif evaluation.state == "in_evaluation" and datetime.now() >= evaluation.vote_end_datetime:
                    evaluation.evaluation_end()
                    if evaluation.is_fully_reviewed:
                        evaluation.review_finished()
                        if not evaluation.wait_for_grade_upload_before_publishing or evaluation.course.final_grade_documents.exists() or evaluation.course.gets_no_grade_documents:
                            evaluation.publish()
                            evaluation_results_evaluations.append(evaluation)
                    evaluation.save()
            except Exception:  # pylint: disable=broad-except
                logger.exception('An error occured when updating the state of evaluation "{}" (id {}).'.format(evaluation, evaluation.id))

        template = EmailTemplate.objects.get(name=EmailTemplate.EVALUATION_STARTED)
        template.send_to_users_in_evaluations(evaluations_new_in_evaluation, [EmailTemplate.Recipients.ALL_PARTICIPANTS], use_cc=False, request=None)

        EmailTemplate.send_participant_publish_notifications(evaluation_results_evaluations)
        EmailTemplate.send_contributor_publish_notifications(evaluation_results_evaluations)

        logger.info("update_evaluations finished.")

    @property
    def unlogged_fields(self):
        return super().unlogged_fields + ["voters", "is_single_result", "can_publish_text_results", "_voter_count", "_participant_count"]


@receiver(post_transition, sender=Evaluation)
def course_was_published(instance, target, **_kwargs):
    """ Evaluation.save checks whether caches must be updated based on this value """
    if target == 'published':
        instance.state_change = "published"


@receiver(post_transition, sender=Evaluation)
def course_was_unpublished(instance, source, **_kwargs):
    """ Evaluation.save checks whether caches must be updated based on this value """
    if source == 'published':
        instance.state_change = "unpublished"


@receiver(post_transition, sender=Evaluation)
def log_state_transition(instance, name, source, target, **_kwargs):
    logger.info('Evaluation "{}" (id {}) moved from state "{}" to state "{}", caused by transition "{}".'.format(instance, instance.pk, source, target, name))


class Contribution(LoggedModel):
    """A contributor who is assigned to an evaluation and his questionnaires."""

    class TextAnswerVisibility(models.TextChoices):
        OWN_TEXTANSWERS = 'OWN', _('Own')
        GENERAL_TEXTANSWERS = 'GENERAL', _('Own and general')

    class Role(models.IntegerChoices):
        CONTRIBUTOR = 0, _('Contributor')
        EDITOR = 1, _('Editor')

    evaluation = models.ForeignKey(Evaluation, models.CASCADE, verbose_name=_("evaluation"), related_name='contributions')
    contributor = models.ForeignKey(settings.AUTH_USER_MODEL, models.PROTECT, verbose_name=_("contributor"), blank=True, null=True,
                                    related_name='contributions')
    questionnaires = models.ManyToManyField(Questionnaire, verbose_name=_("questionnaires"), blank=True, related_name="contributions")
    role = models.IntegerField(choices=Role.choices, verbose_name=_("role"), default=Role.CONTRIBUTOR)
    textanswer_visibility = models.CharField(max_length=10, choices=TextAnswerVisibility.choices, verbose_name=_('text answer visibility'), default=TextAnswerVisibility.OWN_TEXTANSWERS)
    label = models.CharField(max_length=255, blank=True, null=True, verbose_name=_("label"))

    order = models.IntegerField(verbose_name=_("contribution order"), default=-1)

    class Meta:
        unique_together = (
            ('evaluation', 'contributor'),
        )
        ordering = ['order', ]

    @property
    def unlogged_fields(self):
        return super().unlogged_fields + ['evaluation'] + (['contributor'] if self.is_general else [])

    @property
    def is_general(self):
        return self.contributor_id is None

    @property
    def object_to_attach_logentries_to(self):
        return Evaluation, self.evaluation_id

    def __str__(self):
        if self.contributor:
            return _("Contribution by {full_name}").format(full_name=self.contributor.full_name)
        return str(_("General Contribution"))


class Question(models.Model):
    """A question including a type."""

    TEXT = 0
    LIKERT = 1
    GRADE = 2
    EASY_DIFFICULT = 6
    FEW_MANY = 7
    LITTLE_MUCH = 8
    SMALL_LARGE = 9
    SLOW_FAST = 10
    SHORT_LONG = 11
    POSITIVE_YES_NO = 3
    NEGATIVE_YES_NO = 4
    HEADING = 5
    QUESTION_TYPES = (
        (_("Text"), (
            (TEXT, _("Text question")),
        )),
        (_("Unipolar Likert"), (
            (LIKERT, _("Agreement question")),
        )),
        (_("Grade"), (
            (GRADE, _("Grade question")),
        )),
        (_("Bipolar Likert"), (
            (EASY_DIFFICULT, _("Easy-difficult question")),
            (FEW_MANY, _("Few-many question")),
            (LITTLE_MUCH, _("Little-much question")),
            (SMALL_LARGE, _("Small-large question")),
            (SLOW_FAST, _("Slow-fast question")),
            (SHORT_LONG, _("Short-long question")),
        )),
        (_("Yes-no"), (
            (POSITIVE_YES_NO, _("Positive yes-no question")),
            (NEGATIVE_YES_NO, _("Negative yes-no question")),
        )),
        (_("Layout"), (
            (HEADING, _("Heading")),
        ))
    )

    order = models.IntegerField(verbose_name=_("question order"), default=-1)
    questionnaire = models.ForeignKey(Questionnaire, models.CASCADE, related_name="questions")
    text_de = models.CharField(max_length=1024, verbose_name=_("question text (german)"))
    text_en = models.CharField(max_length=1024, verbose_name=_("question text (english)"))
    text = translate(en='text_en', de='text_de')

    type = models.PositiveSmallIntegerField(choices=QUESTION_TYPES, verbose_name=_("question type"))

    class Meta:
        ordering = ['order', ]
        verbose_name = _("question")
        verbose_name_plural = _("questions")

    @property
    def answer_class(self):
        if self.is_text_question:
            return TextAnswer
        if self.is_rating_question:
            return RatingAnswerCounter

        raise Exception("Unknown answer type: %r" % self.type)

    @property
    def is_likert_question(self):
        return self.type == self.LIKERT

    @property
    def is_bipolar_likert_question(self):
        return self.type in (self.EASY_DIFFICULT, self.FEW_MANY, self.LITTLE_MUCH, self.SLOW_FAST, self.SMALL_LARGE, self.SHORT_LONG)

    @property
    def is_text_question(self):
        return self.type == self.TEXT

    @property
    def is_grade_question(self):
        return self.type == self.GRADE

    @property
    def is_positive_yes_no_question(self):
        return self.type == self.POSITIVE_YES_NO

    @property
    def is_negative_yes_no_question(self):
        return self.type == self.NEGATIVE_YES_NO

    @property
    def is_yes_no_question(self):
        return self.is_positive_yes_no_question or self.is_negative_yes_no_question

    @property
    def is_rating_question(self):
        return self.is_grade_question or self.is_bipolar_likert_question or self.is_likert_question or self.is_yes_no_question

    @property
    def is_non_grade_rating_question(self):
        return self.is_rating_question and not self.is_grade_question

    @property
    def is_heading_question(self):
        return self.type == self.HEADING


Choices = namedtuple('Choices', ('cssClass', 'values', 'colors', 'grades', 'names'))
BipolarChoices = namedtuple('BipolarChoices', Choices._fields + ('plus_name', 'minus_name'))

NO_ANSWER = 6
BASE_UNIPOLAR_CHOICES = {
    'cssClass': 'vote-type-unipolar',
    'values': (1, 2, 3, 4, 5, NO_ANSWER),
    'colors': ('green', 'lime', 'yellow', 'orange', 'red', 'gray'),
    'grades': (1, 2, 3, 4, 5)
}

BASE_BIPOLAR_CHOICES = {
    'cssClass': 'vote-type-bipolar',
    'values': (-3, -2, -1, 0, 1, 2, 3, NO_ANSWER),
    'colors': ('red', 'orange', 'lime', 'green', 'lime', 'orange', 'red', 'gray'),
    'grades': (5, 11 / 3, 7 / 3, 1, 7 / 3, 11 / 3, 5)
}

BASE_YES_NO_CHOICES = {
    'cssClass': 'vote-type-yes-no',
    'values': (1, 5, NO_ANSWER),
    'colors': ('green', 'red', 'gray'),
    'grades': (1, 5)
}

CHOICES = {
    Question.LIKERT: Choices(
        names=[
            _("Strongly\nagree"),
            _("Agree"),
            _("Neutral"),
            _("Disagree"),
            _("Strongly\ndisagree"),
            _("No answer")
        ],
        **BASE_UNIPOLAR_CHOICES
    ),
    Question.GRADE: Choices(
        names=[
            "1",
            "2",
            "3",
            "4",
            "5",
            _("No answer")
        ],
        **BASE_UNIPOLAR_CHOICES
    ),
    Question.EASY_DIFFICULT: BipolarChoices(
        minus_name=_("Easy"),
        plus_name=_("Difficult"),
        names=[
            _("Way too\neasy"),
            _("Too\neasy"),
            _("Slightly too\neasy"),
            _("Ideal"),
            _("Slightly too\ndifficult"),
            _("Too\ndifficult"),
            _("Way too\ndifficult"),
            _("No answer")
        ],
        **BASE_BIPOLAR_CHOICES
    ),
    Question.FEW_MANY: BipolarChoices(
        minus_name=_("Few"),
        plus_name=_("Many"),
        names=[
            _("Way too\nfew"),
            _("Too\nfew"),
            _("Slightly too\nfew"),
            _("Ideal"),
            _("Slightly too\nmany"),
            _("Too\nmany"),
            _("Way too\nmany"),
            _("No answer")
        ],
        **BASE_BIPOLAR_CHOICES
    ),
    Question.LITTLE_MUCH: BipolarChoices(
        minus_name=_("Little"),
        plus_name=_("Much"),
        names=[
            _("Way too\nlittle"),
            _("Too\nlittle"),
            _("Slightly too\nlittle"),
            _("Ideal"),
            _("Slightly too\nmuch"),
            _("Too\nmuch"),
            _("Way too\nmuch"),
            _("No answer")
        ],
        **BASE_BIPOLAR_CHOICES
    ),
    Question.SMALL_LARGE: BipolarChoices(
        minus_name=_("Small"),
        plus_name=_("Large"),
        names=[
            _("Way too\nsmall"),
            _("Too\nsmall"),
            _("Slightly too\nsmall"),
            _("Ideal"),
            _("Slightly too\nlarge"),
            _("Too\nlarge"),
            _("Way too\nlarge"),
            _("No answer")
        ],
        **BASE_BIPOLAR_CHOICES
    ),
    Question.SLOW_FAST: BipolarChoices(
        minus_name=_("Slow"),
        plus_name=_("Fast"),
        names=[
            _("Way too\nslow"),
            _("Too\nslow"),
            _("Slightly too\nslow"),
            _("Ideal"),
            _("Slightly too\nfast"),
            _("Too\nfast"),
            _("Way too\nfast"),
            _("No answer")
        ],
        **BASE_BIPOLAR_CHOICES
    ),
    Question.SHORT_LONG: BipolarChoices(
        minus_name=_("Short"),
        plus_name=_("Long"),
        names=[
            _("Way too\nshort"),
            _("Too\nshort"),
            _("Slightly too\nshort"),
            _("Ideal"),
            _("Slightly too\nlong"),
            _("Too\nlong"),
            _("Way too\nlong"),
            _("No answer")
        ],
        **BASE_BIPOLAR_CHOICES
    ),
    Question.POSITIVE_YES_NO: Choices(
        names=[
            _("Yes"),
            _("No"),
            _("No answer")
        ],
        **BASE_YES_NO_CHOICES
    ),
    Question.NEGATIVE_YES_NO: Choices(
        names=[
            _("No"),
            _("Yes"),
            _("No answer")
        ],
        **BASE_YES_NO_CHOICES
    )
}


class Answer(models.Model):
    """An abstract answer to a question. For anonymity purposes, the answering
    user ist not stored in the object. Concrete subclasses are `RatingAnswerCounter`,
    and `TextAnswer`."""

    question = models.ForeignKey(Question, models.PROTECT)
    contribution = models.ForeignKey(Contribution, models.PROTECT, related_name="%(class)s_set")

    class Meta:
        abstract = True
        verbose_name = _("answer")
        verbose_name_plural = _("answers")


class RatingAnswerCounter(Answer):
    """A rating answer counter to a question.
    The interpretation depends on the type of question:
    unipolar: 1, 2, 3, 4, 5; where lower value means more agreement
    bipolar: -3, -2, -1, 0, 1, 2, 3; where a lower absolute means more agreement and the sign shows the pole
    yes / no: 1, 5; for 1 being the good answer"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    answer = models.IntegerField(verbose_name=_("answer"))
    count = models.IntegerField(verbose_name=_("count"), default=0)

    class Meta:
        unique_together = (
            ('question', 'contribution', 'answer'),
        )
        verbose_name = _("rating answer")
        verbose_name_plural = _("rating answers")


class TextAnswer(Answer):
    """A free-form text answer to a question."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    answer = models.TextField(verbose_name=_("answer"))
    original_answer = models.TextField(verbose_name=_("original answer"), blank=True, null=True)

    class State(models.TextChoices):
        HIDDEN = 'HI', _('hidden')
        PUBLISHED = 'PU', _('published')
        PRIVATE = 'PR', _('private')
        NOT_REVIEWED = 'NR', _('not reviewed')

    state = models.CharField(max_length=2, choices=State.choices, verbose_name=_('state of answer'), default=State.NOT_REVIEWED)

    class Meta:
        # Prevent ordering by date for privacy reasons. Otherwise, entries
        # may be returned in insertion order.
        ordering = ['id', ]
        verbose_name = _("text answer")
        verbose_name_plural = _("text answers")

    @property
    def is_hidden(self):
        return self.state == self.State.HIDDEN

    @property
    def is_private(self):
        return self.state == self.State.PRIVATE

    @property
    def is_published(self):
        return self.state == self.State.PUBLISHED

    @property
    def is_reviewed(self):
        return self.state != self.State.NOT_REVIEWED

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        assert self.answer != self.original_answer

    def publish(self):
        self.state = self.State.PUBLISHED

    def hide(self):
        self.state = self.State.HIDDEN

    def make_private(self):
        self.state = self.State.PRIVATE

    def unreview(self):
        self.state = self.State.NOT_REVIEWED


class FaqSection(models.Model):
    """Section in the frequently asked questions"""

    order = models.IntegerField(verbose_name=_("section order"), default=-1)

    title_de = models.CharField(max_length=255, verbose_name=_("section title (german)"))
    title_en = models.CharField(max_length=255, verbose_name=_("section title (english)"))
    title = translate(en='title_en', de='title_de')

    class Meta:
        ordering = ['order', ]
        verbose_name = _("section")
        verbose_name_plural = _("sections")


class FaqQuestion(models.Model):
    """Question and answer in the frequently asked questions"""

    section = models.ForeignKey(FaqSection, models.CASCADE, related_name="questions")

    order = models.IntegerField(verbose_name=_("question order"), default=-1)

    question_de = models.CharField(max_length=1024, verbose_name=_("question (german)"))
    question_en = models.CharField(max_length=1024, verbose_name=_("question (english)"))
    question = translate(en='question_en', de='question_de')

    answer_de = models.TextField(verbose_name=_("answer (german)"))
    answer_en = models.TextField(verbose_name=_("answer (english)"))
    answer = translate(en='answer_en', de='answer_de')

    class Meta:
        ordering = ['order', ]
        verbose_name = _("question")
        verbose_name_plural = _("questions")


class UserProfileManager(BaseUserManager):
    def create_user(self, email, password=None, first_name=None, last_name=None):
        user = self.model(
            email=self.normalize_email(email),
            first_name=first_name,
            last_name=last_name
        )
        user.set_password(password)
        user.save()
        return user

    def create_superuser(self, email, password, first_name=None, last_name=None):
        user = self.create_user(
            password=password,
            email=self.normalize_email(email),
            first_name=first_name,
            last_name=last_name
        )
        user.is_superuser = True
        user.save()
        user.groups.add(Group.objects.get(name="Manager"))
        return user


class UserProfile(AbstractBaseUser, PermissionsMixin):
    # null=True because certain external users don't have an address
    email = models.EmailField(max_length=255, unique=True, blank=True, null=True, verbose_name=_('email address'))

    title = models.CharField(max_length=255, blank=True, null=True, verbose_name=_("Title"))
    first_name = models.CharField(max_length=255, blank=True, null=True, verbose_name=_("first name"))
    last_name = models.CharField(max_length=255, blank=True, null=True, verbose_name=_("last name"))

    language = models.CharField(max_length=8, blank=True, null=True, verbose_name=_("language"))

    # delegates of the user, which can also manage their evaluations
    delegates = models.ManyToManyField("UserProfile", verbose_name=_("Delegates"), related_name="represented_users", blank=True)

    # users to which all emails should be sent in cc without giving them delegate rights
    cc_users = models.ManyToManyField("UserProfile", verbose_name=_("CC Users"), related_name="ccing_users", blank=True)

    # flag for proxy users which represent a group of users
    is_proxy_user = models.BooleanField(default=False, verbose_name=_("Proxy user"))

    # key for url based login of this user
    MAX_LOGIN_KEY = 2**31 - 1

    login_key = models.IntegerField(verbose_name=_("Login Key"), unique=True, blank=True, null=True)
    login_key_valid_until = models.DateField(verbose_name=_("Login Key Validity"), blank=True, null=True)

    is_active = models.BooleanField(default=True, verbose_name=_("active"))

    class Meta:
        ordering = ('last_name', 'first_name', 'email')
        verbose_name = _('user')
        verbose_name_plural = _('users')

    USERNAME_FIELD = 'email'
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

        name = "<unnamed>"
        if self.email:
            name = self.email.split('@')[0]
        if self.is_external:
            name += f" (User {self.id})"
        return name

    @property
    def full_name_with_additional_info(self):
        name = self.full_name
        if self.is_external:
            return name + " [ext.]"
        if '@' in self.email:
            return name + " (" + self.email.split('@')[0] + ")"
        return name + " (" + self.email + ")"

    def __str__(self):
        return self.full_name

    @cached_property
    def is_staff(self):
        return self.is_manager or self.is_reviewer

    @cached_property
    def is_manager(self):
        return self.groups.filter(name='Manager').exists()

    @cached_property
    def is_reviewer(self):
        return self.is_manager or self.groups.filter(name='Reviewer').exists()

    @cached_property
    def is_grade_publisher(self):
        return self.groups.filter(name='Grade publisher').exists()

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
        if not self.is_participant:
            return False

        if not self.is_contributor or self.is_responsible:
            return True

        last_semester_participated = Semester.objects.filter(courses__evaluations__participants=self).order_by("-created_at").first()
        last_semester_contributed = Semester.objects.filter(courses__evaluations__contributions__contributor=self).order_by("-created_at").first()

        return last_semester_participated.created_at >= last_semester_contributed.created_at

    @property
    def is_contributor(self):
        return self.contributions.exists()

    @property
    def is_editor(self):
        return self.contributions.filter(role=Contribution.Role.EDITOR).exists() or self.is_responsible

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
            key = secrets.choice(range(0, UserProfile.MAX_LOGIN_KEY))
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
        return settings.PAGE_URL + reverse('evaluation:login_key_authentication', args=[self.login_key])

    def get_sorted_courses_responsible_for(self):
        return self.courses_responsible_for.order_by('semester__created_at', 'name_de')

    def get_sorted_contributions(self):
        return self.contributions.order_by('evaluation__course__semester__created_at', 'evaluation__name_de')

    def get_sorted_evaluations_participating_in(self):
        return self.evaluations_participating_in.order_by('course__semester__created_at', 'name_de')

    def get_sorted_evaluations_voted_for(self):
        return self.evaluations_voted_for.order_by('course__semester__created_at', 'name_de')

    def get_sorted_due_evaluations(self):
        due_evaluations = dict()
        for evaluation in Evaluation.objects.filter(participants=self, state='in_evaluation').exclude(voters=self):
            due_evaluations[evaluation] = (evaluation.vote_end_date - date.today()).days

        # Sort evaluations by number of days left for evaluation and bring them to following format:
        # [(evaluation, due_in_days), ...]
        return sorted(due_evaluations.items(), key=operator.itemgetter(1))


def validate_template(value):
    """Field validator which ensures that the value can be compiled into a
    Django Template."""
    try:
        Template(value)
    except TemplateSyntaxError as e:
        raise ValidationError(str(e))


class EmailTemplate(models.Model):
    name = models.CharField(max_length=1024, unique=True, verbose_name=_("Name"))

    subject = models.CharField(max_length=1024, verbose_name=_("Subject"), validators=[validate_template])
    body = models.TextField(verbose_name=_("Body"), validators=[validate_template])

    EDITOR_REVIEW_NOTICE = "Editor Review Notice"
    EDITOR_REVIEW_REMINDER = "Editor Review Reminder"
    STUDENT_REMINDER = "Student Reminder"
    PUBLISHING_NOTICE_CONTRIBUTOR = "Publishing Notice Contributor"
    PUBLISHING_NOTICE_PARTICIPANT = "Publishing Notice Participant"
    LOGIN_KEY_CREATED = "Login Key Created"
    EVALUATION_STARTED = "Evaluation Started"
    DIRECT_DELEGATION = "Direct Delegation"

    class Recipients(models.TextChoices):
        ALL_PARTICIPANTS = 'all_participants', _('all participants')
        DUE_PARTICIPANTS = 'due_participants', _('due participants')
        RESPONSIBLE = 'responsible', _('responsible person')
        EDITORS = 'editors', _('all editors')
        CONTRIBUTORS = 'contributors', _('all contributors')

    @classmethod
    def recipient_list_for_evaluation(cls, evaluation, recipient_groups, filter_users_in_cc):
        recipients = set()

        if cls.Recipients.CONTRIBUTORS in recipient_groups or cls.Recipients.EDITORS in recipient_groups or cls.Recipients.RESPONSIBLE in recipient_groups:
            recipients.update(evaluation.course.responsibles.all())
            if cls.Recipients.CONTRIBUTORS in recipient_groups:
                recipients.update(UserProfile.objects.filter(contributions__evaluation=evaluation))
            elif cls.Recipients.EDITORS in recipient_groups:
                recipients.update(UserProfile.objects.filter(
                    contributions__evaluation=evaluation,
                    contributions__role=Contribution.Role.EDITOR,
                ))

        if cls.Recipients.ALL_PARTICIPANTS in recipient_groups:
            recipients.update(evaluation.participants.all())
        elif cls.Recipients.DUE_PARTICIPANTS in recipient_groups:
            recipients.update(evaluation.due_participants)

        if filter_users_in_cc:
            # remove delegates and CC users of recipients from the recipient list
            # so they won't get the exact same email twice
            users_excluded = UserProfile.objects.filter(Q(represented_users__in=recipients) | Q(ccing_users__in=recipients))
            # but do so only if they have no delegates/cc_users, because otherwise
            # those won't get the email at all. consequently, some "edge case users"
            # will get the email twice, but there is no satisfying way around that.
            users_excluded = users_excluded.filter(delegates=None, cc_users=None)

            recipients = recipients - set(users_excluded)

        return list(recipients)

    @staticmethod
    def render_string(text, dictionary):
        return Template(text).render(Context(dictionary, autoescape=False))

    def send_to_users_in_evaluations(self, evaluations, recipient_groups, use_cc, request):
        user_evaluation_map = {}
        for evaluation in evaluations:
            recipients = self.recipient_list_for_evaluation(evaluation, recipient_groups, filter_users_in_cc=use_cc)
            for user in recipients:
                user_evaluation_map.setdefault(user, []).append(evaluation)

        for user, user_evaluations in user_evaluation_map.items():
            subject_params = {}
            body_params = {'user': user, 'evaluations': user_evaluations, 'due_evaluations': user.get_sorted_due_evaluations()}
            self.send_to_user(user, subject_params, body_params, use_cc=use_cc, request=request)

    def send_to_user(self, user, subject_params, body_params, use_cc, additional_cc_users=(), request=None):
        if not user.email:
            warning_message = "{} has no email address defined. Could not send email.".format(user.full_name_with_additional_info)
            # If this method is triggered by a cronjob changing evaluation states, the request is None.
            # In this case warnings should be sent to the admins via email (configured in the settings for logger.error).
            # If a request exists, the page is displayed in the browser and the message can be shown on the page (messages.warning).
            if request is not None:
                logger.warning(warning_message)
                messages.warning(request, _(warning_message))
            else:
                logger.error(warning_message)
            return

        cc_users = set(additional_cc_users)

        if use_cc:
            users = {user, *additional_cc_users}
            cc_users |= set(UserProfile.objects.filter(Q(represented_users__in=users) | Q(ccing_users__in=users)))

        cc_addresses = [p.email for p in cc_users if p.email]

        send_separate_login_url = False
        body_params['login_url'] = ""
        if user.needs_login_key:
            user.ensure_valid_login_key()
            if not cc_addresses:
                body_params['login_url'] = user.login_url
            else:
                send_separate_login_url = True

        subject = self.render_string(self.subject, subject_params)
        body = self.render_string(self.body, body_params)

        mail = EmailMessage(
            subject=subject,
            body=body,
            to=[user.email],
            cc=cc_addresses,
            bcc=[a[1] for a in settings.MANAGERS],
            headers={'Reply-To': settings.REPLY_TO_EMAIL})

        try:
            mail.send(False)
            logger.info(('Sent email "{}" to {}.').format(subject, user.full_name_with_additional_info))
            if send_separate_login_url:
                self.send_login_url_to_user(user)
        except Exception:  # pylint: disable=broad-except
            logger.exception('An exception occurred when sending the following email to user "{}":\n{}\n'.format(user.full_name_with_additional_info, mail.message()))

    @classmethod
    def send_reminder_to_user(cls, user, first_due_in_days, due_evaluations):
        template = cls.objects.get(name=cls.STUDENT_REMINDER)
        subject_params = {'user': user, 'first_due_in_days': first_due_in_days}
        body_params = {'user': user, 'first_due_in_days': first_due_in_days, 'due_evaluations': due_evaluations}

        template.send_to_user(user, subject_params, body_params, use_cc=False)

    @classmethod
    def send_login_url_to_user(cls, user):
        template = cls.objects.get(name=cls.LOGIN_KEY_CREATED)
        subject_params = {}
        body_params = {'user': user, 'login_url': user.login_url}

        template.send_to_user(user, subject_params, body_params, use_cc=False)
        logger.info(('Sent login url to {}.').format(user.email))

    @classmethod
    def send_contributor_publish_notifications(cls, evaluations, template=None):
        if not template:
            template = cls.objects.get(name=cls.PUBLISHING_NOTICE_CONTRIBUTOR)

        evaluations_per_contributor = defaultdict(set)
        for evaluation in evaluations:
            # an average grade is published or a general text answer exists
            relevant_information_published_for_responsibles = (
                evaluation.can_publish_average_grade
                or evaluation.textanswer_set.filter(contribution=evaluation.general_contribution).exists()
            )
            if relevant_information_published_for_responsibles:
                for responsible in evaluation.course.responsibles.all():
                    evaluations_per_contributor[responsible].add(evaluation)

            # for evaluations with published averaged grade, all contributors get a notification
            # we don't send a notification if the significance threshold isn't met
            if evaluation.can_publish_average_grade:
                for contribution in evaluation.contributions.all():
                    if contribution.contributor:
                        evaluations_per_contributor[contribution.contributor].add(evaluation)

            # if the average grade was not published, notifications are only sent for contributors who can see text answers
            elif evaluation.textanswer_set:
                for textanswer in evaluation.textanswer_set:
                    if textanswer.contribution.contributor:
                        evaluations_per_contributor[textanswer.contribution.contributor].add(evaluation)

        for contributor, evaluation_set in evaluations_per_contributor.items():
            body_params = {'user': contributor, 'evaluations': list(evaluation_set)}
            template.send_to_user(contributor, {}, body_params, use_cc=True)

    @classmethod
    def send_participant_publish_notifications(cls, evaluations, template=None):
        if not template:
            template = cls.objects.get(name=cls.PUBLISHING_NOTICE_PARTICIPANT)

        evaluations_per_participant = defaultdict(set)
        for evaluation in evaluations:
            # for evaluations with published averaged grade, participants get a notification
            # we don't send a notification if the significance threshold isn't met
            if evaluation.can_publish_average_grade:
                for participant in evaluation.participants.all():
                    evaluations_per_participant[participant].add(evaluation)

        for participant, evaluation_set in evaluations_per_participant.items():
            body_params = {'user': participant, 'evaluations': list(evaluation_set)}
            template.send_to_user(participant, {}, body_params, use_cc=True)
