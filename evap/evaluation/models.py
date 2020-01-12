from collections import namedtuple
from datetime import datetime, date, timedelta
import logging
import random
import uuid

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, Group, PermissionsMixin
from django.core.cache import caches
from django.core.exceptions import ValidationError
from django.core.mail import EmailMessage
from django.db import models, transaction, IntegrityError
from django.db.models import Count, Q, Manager
from django.dispatch import Signal, receiver
from django.template import Context, Template
from django.template.base import TemplateSyntaxError
from django.utils import timezone
from django.utils.functional import cached_property
from django.utils.translation import ugettext_lazy as _
from django.urls import reverse
from django_fsm import FSMField, transition
from django_fsm.signals import post_transition

from evap.evaluation.tools import clean_email, date_to_datetime, get_due_evaluations_for_user,\
        translate, is_external_email, send_publish_notifications

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

    class Meta:
        ordering = ('-created_at', 'name_de')
        verbose_name = _("semester")
        verbose_name_plural = _("semesters")

    def __str__(self):
        return self.name

    @property
    def can_be_deleted_by_manager(self):
        return self.evaluations.count() == 0 or (self.participations_are_archived and self.grade_documents_are_deleted and self.results_are_archived)

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
    def archive_participations(self):
        if not self.participations_can_be_archived:
            raise NotArchiveable()
        for evaluation in self.evaluations.all():
            evaluation._archive_participations()
        self.participations_are_archived = True
        self.save()

    @transaction.atomic
    def delete_grade_documents(self):
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
        return cls.objects.order_by("created_at").last()

    @property
    def is_active_semester(self):
        return self == Semester.active_semester()

    @property
    def evaluations(self):
        return Evaluation.objects.filter(course__semester=self)


class QuestionnaireManager(Manager):
    def general_questionnaires(self):
        return super().get_queryset().exclude(type=Questionnaire.CONTRIBUTOR)

    def contributor_questionnaires(self):
        return super().get_queryset().filter(type=Questionnaire.CONTRIBUTOR)


class Questionnaire(models.Model):
    """A named collection of questions."""

    TOP = 10
    CONTRIBUTOR = 20
    BOTTOM = 30
    TYPE_CHOICES = (
        (TOP, _('Top questionnaire')),
        (CONTRIBUTOR, _('Contributor questionnaire')),
        (BOTTOM, _('Bottom questionnaire')),
    )
    type = models.IntegerField(choices=TYPE_CHOICES, verbose_name=_('type'), default=TOP)

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

    HIDDEN = 0
    MANAGERS = 1
    EDITORS = 2
    VISIBILITY_CHOICES = (
        (HIDDEN, _("Don't show")),
        (MANAGERS, _("Managers only")),
        (EDITORS, _("Managers and editors")),
    )
    visibility = models.IntegerField(choices=VISIBILITY_CHOICES, verbose_name=_('visibility'), default=MANAGERS)

    objects = QuestionnaireManager()

    class Meta:
        ordering = ('type', 'order', 'name_de')
        verbose_name = _("questionnaire")
        verbose_name_plural = _("questionnaires")

    def __str__(self):
        return self.name

    def __lt__(self, other):
        return (self.type, self.order, self.name_de) < (other.type, other.order, self.name_de)

    def __gt__(self, other):
        return (self.type, self.order, self.name_de) > (other.type, other.order, self.name_de)

    @property
    def is_above_contributors(self):
        return self.type == self.TOP

    @property
    def is_below_contributors(self):
        return self.type == self.BOTTOM

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

    order = models.IntegerField(verbose_name=_("course type order"), default=-1)

    class Meta:
        ordering = ['order', ]

    def __str__(self):
        return self.name

    def can_be_deleted_by_manager(self):
        if not self.pk:
            return True
        return not self.courses.all().exists()


class Course(models.Model):
    """Models a single course, e.g. the Math 101 course of 2002."""
    semester = models.ForeignKey(Semester, models.PROTECT, verbose_name=_("semester"), related_name="courses")

    name_de = models.CharField(max_length=1024, verbose_name=_("name (german)"))
    name_en = models.CharField(max_length=1024, verbose_name=_("name (english)"))
    name = translate(en='name_en', de='name_de')

    # type of course: lecture, seminar, project
    type = models.ForeignKey(CourseType, models.PROTECT, verbose_name=_("course type"), related_name="courses")

    # e.g. Bachelor, Master
    degrees = models.ManyToManyField(Degree, verbose_name=_("degrees"), related_name="courses")

    # default is True as that's the more restrictive option
    is_graded = models.BooleanField(verbose_name=_("is graded"), default=True)

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
        ordering = ('name_de',)
        unique_together = (
            ('semester', 'name_de'),
            ('semester', 'name_en'),
        )
        verbose_name = _("course")
        verbose_name_plural = _("courses")

    def __str__(self):
        return self.name

    def set_last_modified(self, modifying_user):
        self.last_modified_user = modifying_user
        self.last_modified_time = timezone.now()
        logger.info('Course "{}" (id {}) was edited by user {}.'.format(self, self.id, modifying_user.username))

    @property
    def can_be_edited_by_manager(self):
        return not self.semester.participations_are_archived

    @property
    def can_be_deleted_by_manager(self):
        return not self.evaluations.exists()

    @property
    def final_grade_documents(self):
        from evap.grades.models import GradeDocument
        return self.grade_documents.filter(type=GradeDocument.FINAL_GRADES)

    @property
    def midterm_grade_documents(self):
        from evap.grades.models import GradeDocument
        return self.grade_documents.filter(type=GradeDocument.MIDTERM_GRADES)

    @cached_property
    def responsibles_names(self):
        return ", ".join([responsible.full_name for responsible in self.responsibles.all().order_by("last_name")])

    @property
    def has_external_responsible(self):
        return any(responsible.is_external for responsible in self.responsibles.all())

    @property
    def all_evaluations_finished(self):
        return not self.evaluations.exclude(state__in=['evaluated', 'reviewed', 'published']).exists()


class Evaluation(models.Model):
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

    # students that are allowed to vote
    participants = models.ManyToManyField(settings.AUTH_USER_MODEL, verbose_name=_("participants"), blank=True, related_name='evaluations_participating_in')
    _participant_count = models.IntegerField(verbose_name=_("participant count"), blank=True, null=True, default=None)

    # students that already voted
    voters = models.ManyToManyField(settings.AUTH_USER_MODEL, verbose_name=_("voters"), blank=True, related_name='evaluations_voted_for')
    _voter_count = models.IntegerField(verbose_name=_("voter count"), blank=True, null=True, default=None)

    # when the evaluation takes place
    vote_start_datetime = models.DateTimeField(verbose_name=_("start of evaluation"))
    vote_end_date = models.DateField(verbose_name=_("last day of evaluation"))

    # who last modified this evaluation
    last_modified_time = models.DateTimeField(default=timezone.now, verbose_name=_("Last modified"))
    last_modified_user = models.ForeignKey(settings.AUTH_USER_MODEL, models.SET_NULL, null=True, blank=True, related_name="evaluations_last_modified+")

    evaluation_evaluated = Signal(providing_args=['request', 'semester'])

    class Meta:
        # we need an explicit order for, e.g., staff.views.get_evaluations_with_prefetched_data
        ordering = ('pk',)
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
        logger.info('Evaluation "{}" (id {}) was edited by user {}.'.format(self, self.id, modifying_user.username))

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
        return self.general_contribution and (all(self.contributions.annotate(Count('questionnaires')).values_list("questionnaires__count", flat=True)))

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

    def _archive_participations(self):
        """Should be called only via Semester.archive_participations"""
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
            self.textanswer_set.filter(state=TextAnswer.HIDDEN).delete()
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
        return self.contributions.filter(contributor__pk__in=represented_user_pks, can_edit=True).exists() or self.course.responsibles.filter(pk__in=represented_user_pks).exists()

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
        return self.textanswer_set.filter(state=TextAnswer.NOT_REVIEWED)

    @property
    def reviewed_textanswer_set(self):
        return self.textanswer_set.exclude(state=TextAnswer.NOT_REVIEWED)

    @cached_property
    def num_reviewed_textanswers(self):
        return self.reviewed_textanswer_set.count()

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
                        if not evaluation.course.is_graded or evaluation.course.final_grade_documents.exists() or evaluation.course.gets_no_grade_documents:
                            evaluation.publish()
                            evaluation_results_evaluations.append(evaluation)
                    evaluation.save()
            except Exception:  # pylint: disable=broad-except
                logger.exception('An error occured when updating the state of evaluation "{}" (id {}).'.format(evaluation, evaluation.id))

        template = EmailTemplate.objects.get(name=EmailTemplate.EVALUATION_STARTED)
        EmailTemplate.send_to_users_in_evaluations(template, evaluations_new_in_evaluation, [EmailTemplate.ALL_PARTICIPANTS], use_cc=False, request=None)
        send_publish_notifications(evaluation_results_evaluations)
        logger.info("update_evaluations finished.")


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


class Contribution(models.Model):
    """A contributor who is assigned to an evaluation and his questionnaires."""

    OWN_TEXTANSWERS = 'OWN'
    GENERAL_TEXTANSWERS = 'GENERAL'
    TEXTANSWER_VISIBILITY_CHOICES = (
        (OWN_TEXTANSWERS, _('Own')),
        (GENERAL_TEXTANSWERS, _('Own and general')),
    )
    IS_CONTRIBUTOR = 'CONTRIBUTOR'
    IS_EDITOR = 'EDITOR'
    RESPONSIBILITY_CHOICES = (
        (IS_CONTRIBUTOR, _('Contributor')),
        (IS_EDITOR, _('Editor')),
    )

    evaluation = models.ForeignKey(Evaluation, models.CASCADE, verbose_name=_("evaluation"), related_name='contributions')
    contributor = models.ForeignKey(settings.AUTH_USER_MODEL, models.PROTECT, verbose_name=_("contributor"), blank=True, null=True, related_name='contributions')
    questionnaires = models.ManyToManyField(Questionnaire, verbose_name=_("questionnaires"), blank=True, related_name="contributions")
    can_edit = models.BooleanField(verbose_name=_("can edit"), default=False)
    textanswer_visibility = models.CharField(max_length=10, choices=TEXTANSWER_VISIBILITY_CHOICES, verbose_name=_('text answer visibility'), default=OWN_TEXTANSWERS)
    label = models.CharField(max_length=255, blank=True, null=True, verbose_name=_("label"))

    order = models.IntegerField(verbose_name=_("contribution order"), default=-1)

    class Meta:
        unique_together = (
            ('evaluation', 'contributor'),
        )
        ordering = ['order', ]

    @property
    def is_general(self):
        return self.contributor_id is None


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
BipolarChoices = namedtuple('BipolarChoices', Choices._fields + ('plus_name', 'minus_name'))  # pylint: disable=invalid-name

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
            _("no answer")
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
            _("no answer")
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
            _("no answer")
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
            _("no answer")
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
            _("no answer")
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
            _("no answer")
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
            _("no answer")
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
            _("no answer")
        ],
        **BASE_BIPOLAR_CHOICES
    ),
    Question.POSITIVE_YES_NO: Choices(
        names=[
            _("Yes"),
            _("No"),
            _("no answer")
        ],
        **BASE_YES_NO_CHOICES
    ),
    Question.NEGATIVE_YES_NO: Choices(
        names=[
            _("No"),
            _("Yes"),
            _("no answer")
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

    HIDDEN = 'HI'
    PUBLISHED = 'PU'
    PRIVATE = 'PR'
    NOT_REVIEWED = 'NR'
    TEXTANSWER_STATES = (
        (HIDDEN, _('hidden')),
        (PUBLISHED, _('published')),
        (PRIVATE, _('private')),
        (NOT_REVIEWED, _('not reviewed')),
    )
    state = models.CharField(max_length=2, choices=TEXTANSWER_STATES, verbose_name=_('state of answer'), default=NOT_REVIEWED)

    class Meta:
        # Prevent ordering by date for privacy reasons. Otherwise, entries
        # may be returned in insertion order.
        ordering = ['id', ]
        verbose_name = _("text answer")
        verbose_name_plural = _("text answers")

    @property
    def is_hidden(self):
        return self.state == self.HIDDEN

    @property
    def is_private(self):
        return self.state == self.PRIVATE

    @property
    def is_published(self):
        return self.state == self.PUBLISHED

    @property
    def is_reviewed(self):
        return self.state != self.NOT_REVIEWED

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        assert self.answer != self.original_answer

    def publish(self):
        self.state = self.PUBLISHED

    def hide(self):
        self.state = self.HIDDEN

    def make_private(self):
        self.state = self.PRIVATE

    def unreview(self):
        self.state = self.NOT_REVIEWED


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
    def create_user(self, username, password=None, email=None, first_name=None, last_name=None):
        if not username:
            raise ValueError(_('Users must have a username'))

        user = self.model(
            username=username,
            email=self.normalize_email(email),
            first_name=first_name,
            last_name=last_name
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
            last_name=last_name
        )
        user.is_superuser = True
        user.save()
        user.groups.add(Group.objects.get(name="Manager"))
        return user


class UserProfile(AbstractBaseUser, PermissionsMixin):
    username = models.CharField(max_length=255, unique=True, verbose_name=_('username'))

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
        ordering = ('last_name', 'first_name', 'username')
        verbose_name = _('user')
        verbose_name_plural = _('users')

    USERNAME_FIELD = 'username'
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

        return self.username

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

    @classmethod
    def email_needs_login_key(cls, email):
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
        return settings.PAGE_URL + reverse('evaluation:login_key_authentication', args=[self.login_key])

    def get_sorted_courses_responsible_for(self):
        return self.courses_responsible_for.order_by('semester__created_at', 'name_de')

    def get_sorted_contributions(self):
        return self.contributions.order_by('evaluation__course__semester__created_at', 'evaluation__name_de')

    def get_sorted_evaluations_participating_in(self):
        return self.evaluations_participating_in.order_by('course__semester__created_at', 'name_de')

    def get_sorted_evaluations_voted_for(self):
        return self.evaluations_voted_for.order_by('course__semester__created_at', 'name_de')


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

    ALL_PARTICIPANTS = 'all_participants'
    DUE_PARTICIPANTS = 'due_participants'
    RESPONSIBLE = 'responsible'
    EDITORS = 'editors'
    CONTRIBUTORS = 'contributors'

    EMAIL_RECIPIENTS = (
        (ALL_PARTICIPANTS, _('all participants')),
        (DUE_PARTICIPANTS, _('due participants')),
        (RESPONSIBLE, _('responsible person')),
        (EDITORS, _('all editors')),
        (CONTRIBUTORS, _('all contributors'))
    )

    @classmethod
    def recipient_list_for_evaluation(cls, evaluation, recipient_groups, filter_users_in_cc):
        recipients = set()

        if cls.CONTRIBUTORS in recipient_groups or cls.EDITORS in recipient_groups or cls.RESPONSIBLE in recipient_groups:
            recipients.update(evaluation.course.responsibles.all())
            if cls.CONTRIBUTORS in recipient_groups:
                recipients.update(UserProfile.objects.filter(contributions__evaluation=evaluation))
            elif cls.EDITORS in recipient_groups:
                recipients.update(UserProfile.objects.filter(contributions__evaluation=evaluation, contributions__can_edit=True))

        if cls.ALL_PARTICIPANTS in recipient_groups:
            recipients.update(evaluation.participants.all())
        elif cls.DUE_PARTICIPANTS in recipient_groups:
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

    @classmethod
    def render_string(cls, text, dictionary):
        return Template(text).render(Context(dictionary, autoescape=False))

    @classmethod
    def send_to_users_in_evaluations(cls, template, evaluations, recipient_groups, use_cc, request):
        user_evaluation_map = {}
        for evaluation in evaluations:
            recipients = cls.recipient_list_for_evaluation(evaluation, recipient_groups, filter_users_in_cc=use_cc)
            for user in recipients:
                user_evaluation_map.setdefault(user, []).append(evaluation)

        for user, user_evaluations in user_evaluation_map.items():
            subject_params = {}
            body_params = {'user': user, 'evaluations': user_evaluations, 'due_evaluations': get_due_evaluations_for_user(user)}
            cls.send_to_user(user, template, subject_params, body_params, use_cc=use_cc, request=request)

    @classmethod
    def send_to_user(cls, user, template, subject_params, body_params, use_cc, additional_cc_user=None, request=None):
        if not user.email:
            warning_message = "{} has no email address defined. Could not send email.".format(user.username)
            # If this method is triggered by a cronjob changing evaluation states, the request is None.
            # In this case warnings should be sent to the admins via email (configured in the settings for logger.error).
            # If a request exists, the page is displayed in the browser and the message can be shown on the page (messages.warning).
            if request is not None:
                logger.warning(warning_message)
                messages.warning(request, _(warning_message))
            else:
                logger.error(warning_message)
            return

        cc_users = set()

        if additional_cc_user:
            cc_users.add(additional_cc_user)

        if use_cc:
            cc_users |= set(user.delegates.all() | user.cc_users.all())

            if additional_cc_user:
                cc_users |= set(additional_cc_user.delegates.all() | additional_cc_user.cc_users.all())

        cc_addresses = [p.email for p in cc_users if p.email]

        send_separate_login_url = False
        body_params['login_url'] = ""
        if user.needs_login_key:
            user.ensure_valid_login_key()
            if not cc_addresses:
                body_params['login_url'] = user.login_url
            else:
                send_separate_login_url = True

        subject = cls.render_string(template.subject, subject_params)
        body = cls.render_string(template.body, body_params)

        mail = EmailMessage(
            subject=subject,
            body=body,
            to=[user.email],
            cc=cc_addresses,
            bcc=[a[1] for a in settings.MANAGERS],
            headers={'Reply-To': settings.REPLY_TO_EMAIL})

        try:
            mail.send(False)
            logger.info(('Sent email "{}" to {}.').format(subject, user.username))
            if send_separate_login_url:
                cls.send_login_url_to_user(user)
        except Exception:  # pylint: disable=broad-except
            logger.exception('An exception occurred when sending the following email to user "{}":\n{}\n'.format(user.username, mail.message()))

    @classmethod
    def send_reminder_to_user(cls, user, first_due_in_days, due_evaluations):
        template = cls.objects.get(name=cls.STUDENT_REMINDER)
        subject_params = {'user': user, 'first_due_in_days': first_due_in_days}
        body_params = {'user': user, 'first_due_in_days': first_due_in_days, 'due_evaluations': due_evaluations}

        cls.send_to_user(user, template, subject_params, body_params, use_cc=False)

    @classmethod
    def send_login_url_to_user(cls, user):
        template = cls.objects.get(name=cls.LOGIN_KEY_CREATED)
        subject_params = {}
        body_params = {'user': user, 'login_url': user.login_url}

        cls.send_to_user(user, template, subject_params, body_params, use_cc=False)
        logger.info(('Sent login url to {}.').format(user.username))
