import logging
import secrets
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import Enum, auto
from numbers import Real

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, Group, PermissionsMixin
from django.contrib.auth.password_validation import validate_password
from django.contrib.postgres.fields import ArrayField
from django.core.cache import caches
from django.core.exceptions import ValidationError
from django.core.mail import EmailMultiAlternatives
from django.db import IntegrityError, models, transaction
from django.db.models import CheckConstraint, Count, F, Manager, OuterRef, Q, Subquery, Value
from django.db.models.functions import Coalesce, Lower, NullIf, TruncDate
from django.dispatch import Signal, receiver
from django.template import Context, Template
from django.template.defaultfilters import linebreaksbr
from django.template.exceptions import TemplateSyntaxError
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.functional import cached_property
from django.utils.safestring import SafeData
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from django_fsm import FSMIntegerField, transition
from django_fsm.signals import post_transition
from django_stubs_ext import StrOrPromise

from evap.evaluation.models_logging import FieldAction, LoggedModel
from evap.evaluation.tools import (
    clean_email,
    date_to_datetime,
    is_external_email,
    is_prefetched,
    translate,
    vote_end_datetime,
)

logger = logging.getLogger(__name__)


class NotArchivableError(Exception):
    """An attempt has been made to archive something that is not archivable."""


class Semester(models.Model):
    """Represents a semester, e.g. the winter term of 2011/2012."""

    name_de = models.CharField(max_length=1024, unique=True, verbose_name=_("name (german)"))
    name_en = models.CharField(max_length=1024, unique=True, verbose_name=_("name (english)"))
    name = translate(en="name_en", de="name_de")

    short_name_de = models.CharField(max_length=20, unique=True, verbose_name=_("short name (german)"))
    short_name_en = models.CharField(max_length=20, unique=True, verbose_name=_("short name (english)"))
    short_name = translate(en="short_name_en", de="short_name_de")

    participations_are_archived = models.BooleanField(default=False, verbose_name=_("participations are archived"))
    grade_documents_are_deleted = models.BooleanField(default=False, verbose_name=_("grade documents are deleted"))
    results_are_archived = models.BooleanField(default=False, verbose_name=_("results are archived"))

    created_at = models.DateField(verbose_name=_("created at"), auto_now_add=True)

    # (unique=True, blank=True, null=True) allows having multiple non-active but only one active semester
    is_active = models.BooleanField(
        default=None, unique=True, blank=True, null=True, verbose_name=_("semester is active")
    )

    class Meta:
        ordering = ["-created_at", "pk"]
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
        return not self.participations_are_archived and all(
            evaluation.participations_can_be_archived for evaluation in self.evaluations.all()
        )

    @property
    def grade_documents_can_be_deleted(self):
        return not self.grade_documents_are_deleted

    @property
    def results_can_be_archived(self):
        return not self.results_are_archived

    @transaction.atomic
    def archive(self):
        if not self.participations_can_be_archived:
            raise NotArchivableError()
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
            raise NotArchivableError()
        GradeDocument.objects.filter(course__semester=self).delete()
        self.grade_documents_are_deleted = True
        self.save()

    def archive_results(self):
        if not self.results_can_be_archived:
            raise NotArchivableError()
        self.results_are_archived = True
        self.save()

    @classmethod
    def get_all_with_published_unarchived_results(cls):
        return cls.objects.filter(
            courses__evaluations__state=Evaluation.State.PUBLISHED, results_are_archived=False
        ).distinct()

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
        TOP = 10, _("Top questionnaire")
        CONTRIBUTOR = 20, _("Contributor questionnaire")
        BOTTOM = 30, _("Bottom questionnaire")

    type = models.IntegerField(choices=Type.choices, verbose_name=_("type"), default=Type.TOP)

    name_de = models.CharField(max_length=1024, unique=True, verbose_name=_("name (german)"))
    name_en = models.CharField(max_length=1024, unique=True, verbose_name=_("name (english)"))
    name = translate(en="name_en", de="name_de")

    description_de = models.TextField(verbose_name=_("description (german)"), blank=True)
    description_en = models.TextField(verbose_name=_("description (english)"), blank=True)
    description = translate(en="description_en", de="description_de")

    public_name_de = models.CharField(max_length=1024, verbose_name=_("display name (german)"))
    public_name_en = models.CharField(max_length=1024, verbose_name=_("display name (english)"))
    public_name = translate(en="public_name_en", de="public_name_de")

    teaser_de = models.TextField(verbose_name=_("teaser (german)"), blank=True)
    teaser_en = models.TextField(verbose_name=_("teaser (english)"), blank=True)
    teaser = translate(en="teaser_en", de="teaser_de")

    order = models.IntegerField(verbose_name=_("ordering index"), default=0)

    class Visibility(models.IntegerChoices):
        HIDDEN = 0, _("Don't show")
        MANAGERS = 1, _("Managers only")
        EDITORS = 2, _("Managers and editors")

    visibility = models.IntegerField(
        choices=Visibility.choices, verbose_name=_("visibility"), default=Visibility.MANAGERS
    )

    is_locked = models.BooleanField(verbose_name=_("is locked"), default=False)

    objects = QuestionnaireManager()

    def clean(self):
        if self.type == self.Type.CONTRIBUTOR and self.is_locked:
            raise ValidationError({"is_locked": _("Contributor questionnaires cannot be locked.")})

    class Meta:
        ordering = ["type", "order", "pk"]
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
        if is_prefetched(self, "contributions"):
            if all(is_prefetched(contribution, "evaluation") for contribution in self.contributions.all()):
                return all(
                    contribution.evaluation.state == Evaluation.State.NEW for contribution in self.contributions.all()
                )

        return not self.contributions.exclude(evaluation__state=Evaluation.State.NEW).exists()

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
    name = translate(en="name_en", de="name_de")
    import_names = ArrayField(
        models.CharField(max_length=1024), default=list, verbose_name=_("import names"), blank=True
    )

    order = models.IntegerField(verbose_name=_("degree order"), default=-1)

    class Meta:
        ordering = ["order"]

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
    name = translate(en="name_en", de="name_de")
    import_names = ArrayField(
        models.CharField(max_length=1024), default=list, verbose_name=_("import names"), blank=True
    )

    order = models.IntegerField(verbose_name=_("course type order"), default=-1)

    class Meta:
        ordering = ["order"]

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
    name = translate(en="name_en", de="name_de")

    # type of course: lecture, seminar, project
    type = models.ForeignKey(CourseType, models.PROTECT, verbose_name=_("course type"), related_name="courses")

    # e.g. Bachelor, Master
    degrees = models.ManyToManyField(Degree, verbose_name=_("degrees"), related_name="courses")

    # defines whether results can only be seen by contributors and participants
    is_private = models.BooleanField(verbose_name=_("is private"), default=False)

    # persons responsible for the course; their names will be shown next to course, they can edit the course and see general text answers
    responsibles = models.ManyToManyField(
        settings.AUTH_USER_MODEL, verbose_name=_("responsibles"), related_name="courses_responsible_for"
    )

    # grade publishers can set this to True, then the course will be handled as if final grades have already been uploaded
    gets_no_grade_documents = models.BooleanField(verbose_name=_("gets no grade documents"), default=False)

    class Meta:
        unique_together = [
            ["semester", "name_de"],
            ["semester", "name_en"],
        ]
        verbose_name = _("course")
        verbose_name_plural = _("courses")

    def __str__(self):
        return self.name

    @property
    def unlogged_fields(self):
        return super().unlogged_fields + ["semester", "gets_no_grade_documents"]

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
        return ", ".join(responsible.full_name for responsible in self.responsibles.all())

    @property
    def has_external_responsible(self):
        return any(responsible.is_external for responsible in self.responsibles.all())

    @property
    def all_evaluations_finished(self):
        if is_prefetched(self, "evaluations"):
            return all(evaluation.state >= Evaluation.State.EVALUATED for evaluation in self.evaluations.all())

        return not self.evaluations.exclude(state__gte=Evaluation.State.EVALUATED).exists()


class Evaluation(LoggedModel):
    """Models a single evaluation, e.g. the exam evaluation of the Math 101 course of 2002."""

    class State:
        NEW = 10
        PREPARED = 20
        EDITOR_APPROVED = 30
        APPROVED = 40
        IN_EVALUATION = 50
        EVALUATED = 60
        REVIEWED = 70
        PUBLISHED = 80

    state = FSMIntegerField(default=State.NEW, protected=True, verbose_name=_("state"))

    course = models.ForeignKey(Course, models.PROTECT, verbose_name=_("course"), related_name="evaluations")

    # names can be empty, e.g., when there is just one evaluation in a course
    name_de = models.CharField(max_length=1024, verbose_name=_("name (german)"), blank=True)
    name_en = models.CharField(max_length=1024, verbose_name=_("name (english)"), blank=True)
    name = translate(en="name_en", de="name_de")

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
    participants = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        verbose_name=_("participants"),
        blank=True,
        related_name="evaluations_participating_in",
    )
    _participant_count = models.IntegerField(verbose_name=_("participant count"), blank=True, null=True, default=None)

    # students that already voted, or their count after archiving
    voters = models.ManyToManyField(
        settings.AUTH_USER_MODEL, verbose_name=_("voters"), blank=True, related_name="evaluations_voted_for"
    )
    _voter_count = models.IntegerField(verbose_name=_("voter count"), blank=True, null=True, default=None)

    # when the evaluation takes place
    vote_start_datetime = models.DateTimeField(verbose_name=_("start of evaluation"))
    # Usually the property vote_end_datetime should be used instead of this field
    vote_end_date = models.DateField(verbose_name=_("last day of evaluation"))

    # Disable to prevent editors from changing evaluation data
    allow_editors_to_edit = models.BooleanField(verbose_name=_("allow editors to edit"), default=True)

    evaluation_evaluated = Signal()

    # whether to wait for grade uploading before publishing results
    wait_for_grade_upload_before_publishing = models.BooleanField(
        verbose_name=_("wait for grade upload before publishing"), default=True
    )

    class TextAnswerReviewState(Enum):
        do_not_call_in_templates = True  # pylint: disable=invalid-name
        NO_TEXTANSWERS = auto()
        NO_REVIEW_NEEDED = auto()
        REVIEW_NEEDED = auto()
        REVIEW_URGENT = auto()
        REVIEWED = auto()

    class Meta:
        unique_together = [
            ["course", "name_de"],
            ["course", "name_en"],
        ]
        verbose_name = _("evaluation")
        verbose_name_plural = _("evaluations")
        constraints = [
            CheckConstraint(
                check=Q(vote_end_date__gte=TruncDate(F("vote_start_datetime"))),
                name="check_evaluation_start_before_end",
            ),
            CheckConstraint(
                check=~(Q(_participant_count__isnull=True) ^ Q(_voter_count__isnull=True)),
                name="check_evaluation_participant_count_and_voter_count_both_set_or_not_set",
            ),
        ]

    def __str__(self):
        return self.full_name

    def save(self, *args, **kw):
        super().save(*args, **kw)

        # make sure there is a general contribution
        if not self.general_contribution:
            self.contributions.create(contributor=None)
            del self.general_contribution  # invalidate cached property

        if hasattr(self, "state_change_source"):

            def state_changed_to(self, state_set):
                return self.state_change_source not in state_set and self.state in state_set

            def state_changed_from(self, state_set):
                return self.state_change_source in state_set and self.state not in state_set

            # It's clear that results.models will need to reference evaluation.models' classes in ForeignKeys.
            # However, this method only makes sense as a method of Evaluation. Thus, we can't get rid of these imports
            # pylint: disable=import-outside-toplevel
            from evap.results.tools import STATES_WITH_RESULT_TEMPLATE_CACHING, STATES_WITH_RESULTS_CACHING

            if (
                state_changed_to(self, STATES_WITH_RESULTS_CACHING)
                or self.state_change_source == Evaluation.State.EVALUATED
                and self.state == Evaluation.State.REVIEWED
            ):  # reviewing changes results -> cache update required
                from evap.results.tools import cache_results

                cache_results(self)
            elif state_changed_from(self, STATES_WITH_RESULTS_CACHING):
                from evap.results.tools import get_results_cache_key

                caches["results"].delete(get_results_cache_key(self))

            if state_changed_to(self, STATES_WITH_RESULT_TEMPLATE_CACHING):
                from evap.results.views import update_template_cache_of_published_evaluations_in_course

                update_template_cache_of_published_evaluations_in_course(self.course)
            elif state_changed_from(self, STATES_WITH_RESULT_TEMPLATE_CACHING):
                from evap.results.views import (
                    delete_template_cache,
                    update_template_cache_of_published_evaluations_in_course,
                )

                delete_template_cache(self)
                update_template_cache_of_published_evaluations_in_course(self.course)
            del self.state_change_source

    @property
    def full_name(self):
        if self.name:
            return f"{self.course.name} – {self.name}"
        return self.course.name

    @property
    def full_name_de(self):
        if self.name_de:
            return f"{self.course.name_de} – {self.name_de}"
        return self.course.name_de

    @property
    def full_name_en(self):
        if self.name_en:
            return f"{self.course.name_en} – {self.name_en}"
        return self.course.name_en

    @property
    def is_fully_reviewed(self):
        if not self.can_publish_text_results:
            return True
        return not self.unreviewed_textanswer_set.exists()

    @property
    def display_vote_end_datetime(self):
        return date_to_datetime(self.vote_end_date) + timedelta(hours=24)

    @property
    def vote_end_datetime(self):
        return vote_end_datetime(self.vote_end_date)

    @property
    def runtime(self):
        delta = self.vote_end_datetime - self.vote_start_datetime
        return delta.days + 1

    @property
    def is_in_evaluation_period(self):
        return self.vote_start_datetime <= datetime.now() <= self.vote_end_datetime

    @property
    def general_contribution_has_questionnaires(self):
        return self.general_contribution and self.general_contribution.questionnaires.count() > 0

    @property
    def all_contributions_have_questionnaires(self):
        if is_prefetched(self, "contributions"):
            if not self.contributions:
                return False

            if is_prefetched(self.contributions[0], "questionnaires"):
                return all(len(contribution.questionnaires) > 0 for contribution in self.contributions)

        return (
            self.general_contribution is not None
            and not self.contributions.annotate(Count("questionnaires")).filter(questionnaires__count=0).exists()
        )

    def can_be_voted_for_by(self, user):
        """Returns whether the user is allowed to vote on this evaluation."""
        return (
            self.state == Evaluation.State.IN_EVALUATION
            and self.is_in_evaluation_period
            and user in self.participants.all()
            and user not in self.voters.all()
        )

    def can_be_seen_by(self, user):
        if user.is_manager:
            return True
        if self.state == Evaluation.State.NEW:
            return False
        if user.is_reviewer and not self.course.semester.results_are_archived:
            return True
        if self.course.is_private or user.is_external:
            return (
                self.is_user_responsible_or_contributor_or_delegate(user)
                or self.participants.filter(pk=user.pk).exists()
            )
        return True

    def can_results_page_be_seen_by(self, user):
        if self.is_single_result:
            return False
        if user.is_manager:
            return True
        if user.is_reviewer and not self.course.semester.results_are_archived:
            return True
        if self.state != Evaluation.State.PUBLISHED:
            return False
        if not self.can_publish_rating_results or self.course.semester.results_are_archived:
            return self.is_user_responsible_or_contributor_or_delegate(user)
        return self.can_be_seen_by(user)

    @property
    def can_be_edited_by_manager(self):
        return not self.participations_are_archived and self.state < Evaluation.State.PUBLISHED

    @property
    def can_be_deleted_by_manager(self):
        return self.can_be_edited_by_manager and (self.num_voters == 0 or self.is_single_result)

    @cached_property
    def num_participants(self):
        if self._participant_count is not None:
            return self._participant_count

        if is_prefetched(self, "participants"):
            return len(self.participants.all())

        return self.participants.count()

    def _archive(self):
        """Should be called only via Semester.archive"""
        if not self.participations_can_be_archived:
            raise NotArchivableError()
        if self._participant_count is not None:
            assert self._voter_count is not None
            assert (
                self.is_single_result
                or self._voter_count == self.voters.count()
                and self._participant_count == self.participants.count()
            )
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
        return not self.course.semester.participations_are_archived and self.state in [
            Evaluation.State.NEW,
            Evaluation.State.PUBLISHED,
        ]

    @property
    def has_external_participant(self):
        return any(participant.is_external for participant in self.participants.all())

    @property
    def can_staff_see_average_grade(self):
        return self.state >= Evaluation.State.EVALUATED

    @property
    def can_publish_average_grade(self):
        if self.is_single_result:
            return True

        # the average grade is only published if at least the configured percentage of participants voted during the evaluation for significance reasons
        return (
            self.can_publish_rating_results
            and self.num_voters / self.num_participants >= settings.VOTER_PERCENTAGE_NEEDED_FOR_PUBLISHING_AVERAGE_GRADE
        )

    @property
    def can_publish_rating_results(self):
        if self.is_single_result:
            return True

        # the rating results are only published if at least the configured number of participants voted during the evaluation for anonymity reasons
        return self.num_voters >= settings.VOTER_COUNT_NEEDED_FOR_PUBLISHING_RATING_RESULTS

    @transition(field=state, source=[State.NEW, State.EDITOR_APPROVED], target=State.PREPARED)
    def ready_for_editors(self):
        pass

    @transition(field=state, source=State.PREPARED, target=State.EDITOR_APPROVED)
    def editor_approve(self):
        pass

    @transition(
        field=state,
        source=[State.NEW, State.PREPARED, State.EDITOR_APPROVED],
        target=State.APPROVED,
        conditions=[lambda self: self.general_contribution_has_questionnaires],
    )
    def manager_approve(self):
        pass

    @transition(field=state, source=[State.PREPARED, State.EDITOR_APPROVED, State.APPROVED], target=State.NEW)
    def revert_to_new(self):
        pass

    @transition(
        field=state,
        source=State.APPROVED,
        target=State.IN_EVALUATION,
        conditions=[lambda self: self.is_in_evaluation_period],
    )
    def begin_evaluation(self):
        pass

    @transition(
        field=state,
        source=[State.EVALUATED, State.REVIEWED],
        target=State.IN_EVALUATION,
        conditions=[lambda self: self.is_in_evaluation_period],
    )
    def reopen_evaluation(self):
        pass

    @transition(field=state, source=State.IN_EVALUATION, target=State.EVALUATED)
    def end_evaluation(self):
        pass

    @transition(
        field=state, source=State.EVALUATED, target=State.REVIEWED, conditions=[lambda self: self.is_fully_reviewed]
    )
    def end_review(self):
        pass

    @transition(
        field=state,
        source=[State.NEW, State.REVIEWED],
        target=State.REVIEWED,
        conditions=[lambda self: self.is_single_result],
    )
    def skip_review_single_result(self):
        pass

    @transition(
        field=state, source=State.REVIEWED, target=State.EVALUATED, conditions=[lambda self: not self.is_fully_reviewed]
    )
    def reopen_review(self):
        pass

    @transition(field=state, source=State.REVIEWED, target=State.PUBLISHED)
    def publish(self):
        assert self.is_single_result or self._voter_count is None and self._participant_count is None
        self._voter_count = self.num_voters
        self._participant_count = self.num_participants

        if not self.can_publish_text_results:
            self.textanswer_set.delete()
        else:
            self.textanswer_set.filter(review_decision=TextAnswer.ReviewDecision.DELETED).delete()
            self.textanswer_set.update(original_answer=None)

    @transition(field=state, source=State.PUBLISHED, target=State.REVIEWED)
    def unpublish(self):
        assert (
            self.is_single_result
            or self._voter_count == self.voters.count()
            and self._participant_count == self.participants.count()
        )
        self._voter_count = None
        self._participant_count = None

    STATE_STR_CONVERSION = {
        State.NEW: _("new"),
        State.PREPARED: _("prepared"),
        State.EDITOR_APPROVED: _("editor_approved"),
        State.APPROVED: _("approved"),
        State.IN_EVALUATION: _("in_evaluation"),
        State.EVALUATED: _("evaluated"),
        State.REVIEWED: _("reviewed"),
        State.PUBLISHED: _("published"),
    }

    @classmethod
    def state_to_str(cls, state):
        return cls.STATE_STR_CONVERSION[state]

    @property
    def state_str(self):
        return self.state_to_str(self.state)

    @cached_property
    def general_contribution(self):
        if self.pk is None:
            return None

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
    def voter_ratio(self):
        if self.is_single_result or self.num_participants == 0:
            return 0
        return self.num_voters / self.num_participants

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
    def display_time_left_for_evaluation(self):
        return self.display_vote_end_datetime - datetime.now()

    @property
    def time_left_for_evaluation(self):
        return self.vote_end_datetime - datetime.now()

    @property
    def display_hours_left_for_evaluation(self):
        return self.display_time_left_for_evaluation / timedelta(hours=1)

    @property
    def hours_left_for_evaluation(self):
        return self.time_left_for_evaluation / timedelta(hours=1)

    @property
    def ends_soon(self):
        return 0 < self.time_left_for_evaluation.total_seconds() < settings.EVALUATION_END_WARNING_PERIOD * 3600

    @property
    def days_until_evaluation(self):
        days_left = (self.vote_start_datetime.date() - date.today()).days
        if self.vote_start_datetime < datetime.now():
            days_left -= 1
        return days_left

    @property
    def hours_until_evaluation(self):
        return (self.vote_start_datetime - datetime.now()) / timedelta(hours=1)

    def is_user_editor_or_delegate(self, user):
        represented_users = user.represented_users.all() | UserProfile.objects.filter(pk=user.pk)
        return (
            self.contributions.filter(contributor__in=represented_users, role=Contribution.Role.EDITOR).exists()
            or self.course.responsibles.filter(pk__in=represented_users).exists()
        )

    def is_user_responsible_or_contributor_or_delegate(self, user):
        # early out that saves database hits since is_responsible_or_contributor_or_delegate is a cached_property
        if not user.is_responsible_or_contributor_or_delegate:
            return False
        represented_users = user.represented_users.all() | UserProfile.objects.filter(pk=user.pk)
        return (
            self.contributions.filter(contributor__in=represented_users).exists()
            or self.course.responsibles.filter(pk__in=represented_users).exists()
        )

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
        return self.textanswer_set.filter(review_decision=TextAnswer.ReviewDecision.UNDECIDED)

    @property
    def reviewed_textanswer_set(self):
        return self.textanswer_set.exclude(review_decision=TextAnswer.ReviewDecision.UNDECIDED)

    @cached_property
    def num_reviewed_textanswers(self):
        return self.reviewed_textanswer_set.count()

    @property
    def textanswer_review_state(self):
        if self.num_textanswers == 0:
            return self.TextAnswerReviewState.NO_TEXTANSWERS

        if self.num_textanswers == self.num_reviewed_textanswers:
            return self.TextAnswerReviewState.REVIEWED

        if self.state < Evaluation.State.EVALUATED:
            return self.TextAnswerReviewState.NO_REVIEW_NEEDED

        if self.state == Evaluation.State.EVALUATED and self.grading_process_is_finished:
            return self.TextAnswerReviewState.REVIEW_URGENT

        return self.TextAnswerReviewState.REVIEW_NEEDED

    @property
    def ratinganswer_counters(self):
        return RatingAnswerCounter.objects.filter(contribution__evaluation=self)

    @property
    def grading_process_is_finished(self):
        return (
            not self.wait_for_grade_upload_before_publishing
            or self.course.gets_no_grade_documents
            or self.course.final_grade_documents.exists()
        )

    @classmethod
    def update_evaluations(cls):
        logger.info("update_evaluations called. Processing evaluations now.")

        evaluations_new_in_evaluation = []
        evaluation_results_evaluations = []

        for evaluation in cls.objects.all():
            try:
                if evaluation.state == Evaluation.State.APPROVED and evaluation.vote_start_datetime <= datetime.now():
                    evaluation.begin_evaluation()
                    evaluation.save()
                    evaluations_new_in_evaluation.append(evaluation)
                elif (
                    evaluation.state == Evaluation.State.IN_EVALUATION
                    and datetime.now() >= evaluation.vote_end_datetime
                ):
                    evaluation.end_evaluation()
                    if evaluation.is_fully_reviewed:
                        evaluation.end_review()
                        if evaluation.grading_process_is_finished:
                            evaluation.publish()
                            evaluation_results_evaluations.append(evaluation)
                    evaluation.save()
            except Exception:  # pylint: disable=broad-except
                logger.exception(
                    'An error occured when updating the state of evaluation "%s" (id %d).', evaluation, evaluation.id
                )

        template = EmailTemplate.objects.get(name=EmailTemplate.EVALUATION_STARTED)
        template.send_to_users_in_evaluations(
            evaluations_new_in_evaluation, [EmailTemplate.Recipients.ALL_PARTICIPANTS], use_cc=False, request=None
        )

        EmailTemplate.send_participant_publish_notifications(evaluation_results_evaluations)
        EmailTemplate.send_contributor_publish_notifications(evaluation_results_evaluations)

        logger.info("update_evaluations finished.")

    @classmethod
    def annotate_with_participant_and_voter_counts(cls, evaluation_query):
        subquery = Evaluation.objects.filter(pk=OuterRef("pk"))

        participant_count_subquery = subquery.annotate(
            num_participants=Coalesce("_participant_count", Count("participants")),
        ).values("num_participants")

        voter_count_subquery = subquery.annotate(
            num_voters=Coalesce("_voter_count", Count("voters")),
        ).values("num_voters")

        return evaluation_query.annotate(
            num_participants=Subquery(participant_count_subquery),
            num_voters=Subquery(voter_count_subquery),
        )

    @property
    def unlogged_fields(self):
        return super().unlogged_fields + [
            "voters",
            "is_single_result",
            "can_publish_text_results",
            "_voter_count",
            "_participant_count",
        ]

    @classmethod
    def transform_log_action(cls, field_action):
        if field_action.label.lower() == Evaluation.state.field.verbose_name.lower():
            return FieldAction(
                field_action.label, field_action.type, [cls.state_to_str(state) for state in field_action.items]
            )
        return field_action


@receiver(post_transition, sender=Evaluation)
def evaluation_state_change(instance, source, **_kwargs):
    """Evaluation.save checks whether caches must be updated based on this value"""
    # if multiple state changes are happening, state_change_source should be the first source
    if not hasattr(instance, "state_change_source"):
        instance.state_change_source = source


@receiver(post_transition, sender=Evaluation)
def log_state_transition(instance, name, source, target, **_kwargs):
    logger.info(
        'Evaluation "%s" (id %d) moved from state "%s" to state "%s", caused by transition "%s".',
        instance,
        instance.pk,
        source,
        target,
        name,
    )


class Contribution(LoggedModel):
    """A contributor who is assigned to an evaluation and his questionnaires."""

    class TextAnswerVisibility(models.TextChoices):
        OWN_TEXTANSWERS = "OWN", _("Own")
        GENERAL_TEXTANSWERS = "GENERAL", _("Own and general")

    class Role(models.IntegerChoices):
        CONTRIBUTOR = 0, _("Contributor")
        EDITOR = 1, _("Editor")

    evaluation = models.ForeignKey(
        Evaluation, models.CASCADE, verbose_name=_("evaluation"), related_name="contributions"
    )
    contributor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        models.PROTECT,
        verbose_name=_("contributor"),
        blank=True,
        null=True,
        related_name="contributions",
    )
    questionnaires = models.ManyToManyField(
        Questionnaire, verbose_name=_("questionnaires"), blank=True, related_name="contributions"
    )
    role = models.IntegerField(choices=Role.choices, verbose_name=_("role"), default=Role.CONTRIBUTOR)
    textanswer_visibility = models.CharField(
        max_length=10,
        choices=TextAnswerVisibility.choices,
        verbose_name=_("text answer visibility"),
        default=TextAnswerVisibility.OWN_TEXTANSWERS,
    )
    label = models.CharField(max_length=255, blank=True, verbose_name=_("label"))

    order = models.IntegerField(verbose_name=_("contribution order"), default=-1)

    class Meta:
        unique_together = [["evaluation", "contributor"]]
        ordering = ["order"]
        verbose_name = _("contribution")
        verbose_name_plural = _("contributions")

    @property
    def unlogged_fields(self):
        return super().unlogged_fields + ["evaluation"] + (["contributor"] if self.is_general else [])

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

    def remove_answers_to_questionnaires(self, questionnaires):
        assert set(Answer.__subclasses__()) == {TextAnswer, RatingAnswerCounter}
        TextAnswer.objects.filter(contribution=self, question__questionnaire__in=questionnaires).delete()
        RatingAnswerCounter.objects.filter(contribution=self, question__questionnaire__in=questionnaires).delete()


class QuestionType:
    TEXT = 0
    POSITIVE_LIKERT = 1
    NEGATIVE_LIKERT = 12
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


class Question(models.Model):
    """A question including a type."""

    QUESTION_TYPES = (
        (_("Text"), ((QuestionType.TEXT, _("Text question")),)),
        (
            _("Unipolar Likert"),
            (
                (QuestionType.POSITIVE_LIKERT, _("Positive agreement question")),
                (QuestionType.NEGATIVE_LIKERT, _("Negative agreement question")),
            ),
        ),
        (_("Grade"), ((QuestionType.GRADE, _("Grade question")),)),
        (
            _("Bipolar Likert"),
            (
                (QuestionType.EASY_DIFFICULT, _("Easy-difficult question")),
                (QuestionType.FEW_MANY, _("Few-many question")),
                (QuestionType.LITTLE_MUCH, _("Little-much question")),
                (QuestionType.SMALL_LARGE, _("Small-large question")),
                (QuestionType.SLOW_FAST, _("Slow-fast question")),
                (QuestionType.SHORT_LONG, _("Short-long question")),
            ),
        ),
        (
            _("Yes-no"),
            (
                (QuestionType.POSITIVE_YES_NO, _("Positive yes-no question")),
                (QuestionType.NEGATIVE_YES_NO, _("Negative yes-no question")),
            ),
        ),
        (_("Layout"), ((QuestionType.HEADING, _("Heading")),)),
    )

    order = models.IntegerField(verbose_name=_("question order"), default=-1)
    questionnaire = models.ForeignKey(Questionnaire, models.CASCADE, related_name="questions")
    text_de = models.CharField(max_length=1024, verbose_name=_("question text (german)"))
    text_en = models.CharField(max_length=1024, verbose_name=_("question text (english)"))
    text = translate(en="text_en", de="text_de")
    allows_additional_textanswers = models.BooleanField(default=True, verbose_name=_("allow additional text answers"))

    type = models.PositiveSmallIntegerField(choices=QUESTION_TYPES, verbose_name=_("question type"))

    class Meta:
        ordering = ["order"]
        verbose_name = _("question")
        verbose_name_plural = _("questions")
        constraints = [
            CheckConstraint(
                check=~(Q(type=QuestionType.TEXT) | Q(type=QuestionType.HEADING))
                | ~Q(allows_additional_textanswers=True),
                name="check_evaluation_textanswer_or_heading_question_has_no_additional_textanswers",
            )
        ]

    def save(self, *args, **kwargs):
        if self.type in [QuestionType.TEXT, QuestionType.HEADING]:
            self.allows_additional_textanswers = False
            if "update_fields" in kwargs:
                kwargs["update_fields"] = {"allows_additional_textanswers"}.union(kwargs["update_fields"])

        super().save(*args, **kwargs)

    @property
    def answer_class(self):
        if self.is_text_question:
            return TextAnswer
        if self.is_rating_question:
            return RatingAnswerCounter

        raise AssertionError(f"Unknown answer type: {self.type!r}")

    @property
    def is_positive_likert_question(self):
        return self.type == QuestionType.POSITIVE_LIKERT

    @property
    def is_negative_likert_question(self):
        return self.type == QuestionType.NEGATIVE_LIKERT

    @property
    def is_bipolar_likert_question(self):
        return self.type in (
            QuestionType.EASY_DIFFICULT,
            QuestionType.FEW_MANY,
            QuestionType.LITTLE_MUCH,
            QuestionType.SLOW_FAST,
            QuestionType.SMALL_LARGE,
            QuestionType.SHORT_LONG,
        )

    @property
    def is_text_question(self):
        return self.type == QuestionType.TEXT

    @property
    def is_grade_question(self):
        return self.type == QuestionType.GRADE

    @property
    def is_positive_yes_no_question(self):
        return self.type == QuestionType.POSITIVE_YES_NO

    @property
    def is_negative_yes_no_question(self):
        return self.type == QuestionType.NEGATIVE_YES_NO

    @property
    def is_yes_no_question(self):
        return self.is_positive_yes_no_question or self.is_negative_yes_no_question

    @property
    def is_rating_question(self):
        return (
            self.is_grade_question
            or self.is_bipolar_likert_question
            or self.is_positive_likert_question
            or self.is_negative_likert_question
            or self.is_yes_no_question
        )

    @property
    def is_non_grade_rating_question(self):
        return self.is_rating_question and not self.is_grade_question

    @property
    def is_heading_question(self):
        return self.type == QuestionType.HEADING

    @property
    def can_have_textanswers(self):
        return self.is_text_question or self.is_rating_question and self.allows_additional_textanswers


@dataclass
class Choices:
    css_class: str
    values: tuple[Real]
    colors: tuple[str]
    grades: tuple[Real]
    names: list[StrOrPromise]
    is_inverted: bool

    def as_name_color_value_tuples(self):
        return zip(self.names, self.colors, self.values, strict=True)


@dataclass
class BipolarChoices(Choices):
    plus_name: StrOrPromise
    minus_name: StrOrPromise


NO_ANSWER = 6
BASE_UNIPOLAR_CHOICES = {
    "css_class": "vote-type-unipolar",
    "values": (1, 2, 3, 4, 5, NO_ANSWER),
    "colors": ("green", "lime", "yellow", "orange", "red", "gray"),
    "grades": (1, 2, 3, 4, 5),
}

BASE_BIPOLAR_CHOICES = {
    "css_class": "vote-type-bipolar",
    "values": (-3, -2, -1, 0, 1, 2, 3, NO_ANSWER),
    "colors": ("red", "orange", "lime", "green", "lime", "orange", "red", "gray"),
    "grades": (5, 11 / 3, 7 / 3, 1, 7 / 3, 11 / 3, 5),
    "is_inverted": False,
}

BASE_YES_NO_CHOICES = {
    "css_class": "vote-type-yes-no",
    "values": (1, 5, NO_ANSWER),
    "colors": ("green", "red", "gray"),
    "grades": (1, 5),
}

CHOICES: dict[int, Choices | BipolarChoices] = {
    QuestionType.POSITIVE_LIKERT: Choices(
        names=[
            _("Strongly\nagree"),
            _("Agree"),
            _("Neutral"),
            _("Disagree"),
            _("Strongly\ndisagree"),
            _("No answer"),
        ],
        is_inverted=False,
        **BASE_UNIPOLAR_CHOICES,  # type: ignore
    ),
    QuestionType.NEGATIVE_LIKERT: Choices(
        names=[
            _("Strongly\ndisagree"),
            _("Disagree"),
            _("Neutral"),
            _("Agree"),
            _("Strongly\nagree"),
            _("No answer"),
        ],
        is_inverted=True,
        **BASE_UNIPOLAR_CHOICES,  # type: ignore
    ),
    QuestionType.GRADE: Choices(
        names=[
            "1",
            "2",
            "3",
            "4",
            "5",
            _("No answer"),
        ],
        is_inverted=False,
        **BASE_UNIPOLAR_CHOICES,  # type: ignore
    ),
    QuestionType.EASY_DIFFICULT: BipolarChoices(
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
            _("No answer"),
        ],
        **BASE_BIPOLAR_CHOICES,  # type: ignore
    ),
    QuestionType.FEW_MANY: BipolarChoices(
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
            _("No answer"),
        ],
        **BASE_BIPOLAR_CHOICES,  # type: ignore
    ),
    QuestionType.LITTLE_MUCH: BipolarChoices(
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
            _("No answer"),
        ],
        **BASE_BIPOLAR_CHOICES,  # type: ignore
    ),
    QuestionType.SMALL_LARGE: BipolarChoices(
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
            _("No answer"),
        ],
        **BASE_BIPOLAR_CHOICES,  # type: ignore
    ),
    QuestionType.SLOW_FAST: BipolarChoices(
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
            _("No answer"),
        ],
        **BASE_BIPOLAR_CHOICES,  # type: ignore
    ),
    QuestionType.SHORT_LONG: BipolarChoices(
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
            _("No answer"),
        ],
        **BASE_BIPOLAR_CHOICES,  # type: ignore
    ),
    QuestionType.POSITIVE_YES_NO: Choices(
        names=[
            _("Yes"),
            _("No"),
            _("No answer"),
        ],
        is_inverted=False,
        **BASE_YES_NO_CHOICES,  # type: ignore
    ),
    QuestionType.NEGATIVE_YES_NO: Choices(
        names=[
            _("No"),
            _("Yes"),
            _("No answer"),
        ],
        is_inverted=True,
        **BASE_YES_NO_CHOICES,  # type: ignore
    ),
}


class Answer(models.Model):
    """
    An abstract answer to a question. For anonymity purposes, the answering
    user ist not stored in the object. Concrete subclasses are
    `RatingAnswerCounter`, and `TextAnswer`.
    """

    # we use UUIDs to hide insertion order. See https://github.com/e-valuation/EvaP/wiki/Data-Economy
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    question = models.ForeignKey(Question, models.PROTECT)
    contribution = models.ForeignKey(Contribution, models.PROTECT, related_name="%(class)s_set")

    class Meta:
        abstract = True
        verbose_name = _("answer")
        verbose_name_plural = _("answers")


class RatingAnswerCounter(Answer):
    """
    A rating answer counter to a question.
    The interpretation depends on the type of question:
    unipolar: 1, 2, 3, 4, 5; where lower value means more agreement
    bipolar: -3, -2, -1, 0, 1, 2, 3; where a lower absolute means more agreement and the sign shows the pole
    yes / no: 1, 5; for 1 being the good answer
    """

    answer = models.IntegerField(verbose_name=_("answer"))
    count = models.IntegerField(verbose_name=_("count"), default=0)

    class Meta:
        unique_together = [["question", "contribution", "answer"]]
        verbose_name = _("rating answer")
        verbose_name_plural = _("rating answers")


class TextAnswer(Answer):
    """A free-form text answer to a question."""

    answer = models.TextField(verbose_name=_("answer"))
    # If the text answer was changed during review, original_answer holds the original text. Otherwise, it's null.
    original_answer = models.TextField(verbose_name=_("original answer"), blank=True, null=True)

    class ReviewDecision(models.TextChoices):
        """
        When publishing evaluation results, this answer should be ...
        """

        PUBLIC = "PU", _("public")
        PRIVATE = "PR", _("private")  # This answer should only be displayed to the contributor the question was about
        DELETED = "DE", _("deleted")

        UNDECIDED = "UN", _("undecided")

    review_decision = models.CharField(
        max_length=2,
        choices=ReviewDecision.choices,
        verbose_name=_("review decision for the answer"),
        default=ReviewDecision.UNDECIDED,
    )

    # Staff users marked this answer for internal purposes; the meaning of the flag is determined by users
    is_flagged = models.BooleanField(verbose_name=_("is flagged"), default=False)

    class Meta:
        # Prevent ordering by date for privacy reasons. Otherwise, entries
        # may be returned in insertion order.
        ordering = ["id"]
        verbose_name = _("text answer")
        verbose_name_plural = _("text answers")
        constraints = [
            CheckConstraint(check=~Q(answer=F("original_answer")), name="check_evaluation_text_answer_is_modified")
        ]

    @property
    def will_be_deleted(self):
        return self.review_decision == self.ReviewDecision.DELETED

    @property
    def will_be_private(self):
        return self.review_decision == self.ReviewDecision.PRIVATE

    @property
    def will_be_public(self):
        return self.review_decision == self.ReviewDecision.PUBLIC

    # Once evaluation results are published, the review decision is executed
    # and thus, an answer _is_ private or _is_ public from that point on.
    @property
    def is_public(self):
        return self.will_be_public

    @property
    def is_private(self):
        return self.will_be_private

    @property
    def is_reviewed(self):
        return self.review_decision != self.ReviewDecision.UNDECIDED

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)


class FaqSection(models.Model):
    """Section in the frequently asked questions"""

    order = models.IntegerField(verbose_name=_("section order"), default=-1)

    title_de = models.CharField(max_length=255, verbose_name=_("section title (german)"))
    title_en = models.CharField(max_length=255, verbose_name=_("section title (english)"))
    title = translate(en="title_en", de="title_de")

    class Meta:
        ordering = ["order"]
        verbose_name = _("section")
        verbose_name_plural = _("sections")


class FaqQuestion(models.Model):
    """Question and answer in the frequently asked questions"""

    section = models.ForeignKey(FaqSection, models.CASCADE, related_name="questions")

    order = models.IntegerField(verbose_name=_("question order"), default=-1)

    question_de = models.CharField(max_length=1024, verbose_name=_("question (german)"))
    question_en = models.CharField(max_length=1024, verbose_name=_("question (english)"))
    question = translate(en="question_en", de="question_de")

    answer_de = models.TextField(verbose_name=_("answer (german)"))
    answer_en = models.TextField(verbose_name=_("answer (english)"))
    answer = translate(en="answer_en", de="answer_de")

    class Meta:
        ordering = ["order"]
        verbose_name = _("question")
        verbose_name_plural = _("questions")


class NotHalfEmptyConstraint(CheckConstraint):
    """Constraint, that all supplied fields are either all filled, or all empty."""

    fields: list[str] = []

    def __init__(self, *, fields: list[str], name: str, **kwargs):
        self.fields = fields
        assert "check" not in kwargs

        super().__init__(
            check=Q(**{field: "" for field in fields}) | ~Q(**{field: "" for field in fields}, _connector=Q.OR),
            name=name,
            **kwargs,
        )

    def deconstruct(self):
        path, args, kwargs = super().deconstruct()
        kwargs.pop("check")
        kwargs["fields"] = self.fields
        return path, args, kwargs

    def validate(self, model, instance, exclude=None, using=None):
        try:
            super().validate(model, instance, exclude, using)
        except ValidationError as e:
            e.error_dict = {
                field_name: ValidationError(instance._meta.get_field(field_name).error_messages["blank"], code="blank")
                for field_name in self.fields
                if getattr(instance, field_name) == ""
            }
            raise e


class Infotext(models.Model):
    """Infotext to display, e.g., at the student index and contributor index pages"""

    title_de = models.CharField(max_length=255, verbose_name=_("title (german)"), blank=True)
    title_en = models.CharField(max_length=255, verbose_name=_("title (english)"), blank=True)
    title = translate(en="title_en", de="title_de", blank=True)

    content_de = models.TextField(verbose_name=_("content (german)"), blank=True)
    content_en = models.TextField(verbose_name=_("content (english)"), blank=True)
    content = translate(en="content_en", de="content_de")

    def is_empty(self):
        return not (self.title or self.content)

    class Page(models.TextChoices):
        STUDENT_INDEX = ("student_index", "Student index page")
        CONTRIBUTOR_INDEX = ("contributor_index", "Contributor index page")
        GRADES_PAGES = ("grades_pages", "Grade publishing pages")

    page = models.CharField(
        choices=Page.choices,
        verbose_name="page for the infotext to be visible on",
        max_length=30,
        unique=True,
        null=False,
        blank=False,
    )

    class Meta:
        verbose_name = _("infotext")
        verbose_name_plural = _("infotexts")
        constraints = (
            NotHalfEmptyConstraint(
                name="infotext_not_half_empty",
                fields=["title_de", "title_en", "content_de", "content_en"],
            ),
        )


class UserProfileManager(BaseUserManager):
    def create_user(self, *, email, password=None, first_name=None, last_name=None):
        user = self.model(email=self.normalize_email(email), first_name_given=first_name, last_name=last_name)
        validate_password(password, user=user)
        user.set_password(password)
        user.save()
        return user

    def create_superuser(self, *, email, password=None, first_name=None, last_name=None):
        user = self.create_user(
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
    # null=True because certain external users don't have an address
    email = models.EmailField(max_length=255, unique=True, blank=True, null=True, verbose_name=_("email address"))

    title = models.CharField(max_length=255, blank=True, default="", verbose_name=_("Title"))
    first_name_given = models.CharField(max_length=255, blank=True, verbose_name=_("first name"))
    first_name_chosen = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name=_("display name"),
        help_text=_("This will replace your first name."),
    )
    last_name = models.CharField(max_length=255, blank=True, verbose_name=_("last name"))

    language = models.CharField(max_length=8, blank=True, default="", verbose_name=_("language"))

    # delegates of the user, which can also manage their evaluations
    delegates = models.ManyToManyField(
        "evaluation.UserProfile", verbose_name=_("Delegates"), related_name="represented_users", blank=True
    )

    # users to which all emails should be sent in cc without giving them delegate rights
    cc_users = models.ManyToManyField(
        "evaluation.UserProfile", verbose_name=_("CC Users"), related_name="ccing_users", blank=True
    )

    # flag for proxy users which represent a group of users
    is_proxy_user = models.BooleanField(default=False, verbose_name=_("Proxy user"))

    # key for url based login of this user
    MAX_LOGIN_KEY = 2**31 - 1

    login_key = models.IntegerField(verbose_name=_("Login Key"), unique=True, blank=True, null=True)
    login_key_valid_until = models.DateField(verbose_name=_("Login Key Validity"), blank=True, null=True)

    is_active = models.BooleanField(default=True, verbose_name=_("active"))

    notes = models.TextField(verbose_name=_("notes"), blank=True, default="", max_length=1024 * 1024)

    class StartPage(models.TextChoices):
        DEFAULT = "DE", _("default")
        STUDENT = "ST", _("student")
        CONTRIBUTOR = "CO", _("contributor")
        GRADES = "GR", _("grades")

    startpage = models.CharField(
        max_length=2,
        choices=StartPage.choices,
        verbose_name=_("start page of the user"),
        default=StartPage.DEFAULT,
    )

    class Meta:
        # keep in sync with ordering_key
        ordering = [
            Lower(NullIf("last_name", Value(""))),
            Lower(Coalesce(NullIf("first_name_chosen", Value("")), NullIf("first_name_given", Value("")))),
            Lower("email"),
        ]

        verbose_name = _("user")
        verbose_name_plural = _("users")

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserProfileManager()

    def save(self, *args, **kwargs):
        # This is not guaranteed to be called on every insert. For example, the importers use bulk insertion.

        self.email = clean_email(self.email)
        super().save(*args, **kwargs)

    @property
    def first_name(self):
        return self.first_name_chosen or self.first_name_given

    def ordering_key(self):
        # keep in sync with Meta.ordering
        lower_last_name = (self.last_name or "").lower()
        lower_first_name = (self.first_name or "").lower()
        lower_email = (self.email or "").lower()
        return (lower_last_name, lower_first_name, lower_email)

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
            name = self.email.split("@")[0]
        if self.is_external:
            name += f" (User {self.id})"
        return name

    @property
    def full_name_with_additional_info(self):
        name = self.full_name
        if self.is_external:
            return name + " [ext.]"
        return f"{name} ({self.email})"

    def __str__(self):
        return self.full_name

    @cached_property
    def is_staff(self):
        return self.is_manager or self.is_reviewer

    # Required for staff mode to work, since several other cached properties (including is_staff) are overwritten
    @property
    def has_staff_permission(self):
        return self.groups.filter(name="Manager").exists() or self.groups.filter(name="Reviewer").exists()

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
        if (
            self.is_responsible
            or self.is_contributor
            or self.is_reviewer
            or self.is_grade_publisher
            or self.is_superuser
        ):
            return False
        if any(not evaluation.participations_are_archived for evaluation in self.evaluations_participating_in.all()):
            return False
        if self.is_proxy_user:
            return False
        return True

    @cached_property
    def is_participant(self):
        return self.evaluations_participating_in.exists()

    @cached_property
    def is_student(self):
        """
        A UserProfile is not considered to be a student anymore if the
        newest contribution is newer than the newest participation.
        """
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

    @cached_property
    def is_contributor(self):
        return self.contributions.exists()

    @cached_property
    def is_editor(self):
        return self.contributions.filter(role=Contribution.Role.EDITOR).exists() or self.is_responsible

    @cached_property
    def is_responsible(self):
        return self.courses_responsible_for.exists()

    @cached_property
    def is_delegate(self):
        return self.represented_users.exists()

    @cached_property
    def is_editor_or_delegate(self):
        return self.is_editor or self.is_delegate

    @cached_property
    def is_responsible_or_contributor_or_delegate(self):
        return self.is_responsible or self.is_contributor or self.is_delegate

    @cached_property
    def show_startpage_button(self):
        return [self.is_participant, self.is_responsible_or_contributor_or_delegate, self.is_grade_publisher].count(
            True
        ) > 1

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
        evaluations_and_days_left = (
            (evaluation, evaluation.days_left_for_evaluation)
            for evaluation in Evaluation.objects.filter(
                participants=self, state=Evaluation.State.IN_EVALUATION
            ).exclude(voters=self)
        )
        return sorted(evaluations_and_days_left, key=lambda tup: (tup[1], tup[0].full_name))


def validate_template(value):
    """Field validator which ensures that the value can be compiled into a
    Django Template."""
    try:
        Template(value)
    except TemplateSyntaxError as e:
        raise ValidationError(str(e)) from e


class EmailTemplate(models.Model):
    name = models.CharField(max_length=1024, unique=True, verbose_name=_("Name"))

    subject = models.CharField(max_length=1024, verbose_name=_("Subject"), validators=[validate_template])
    plain_content = models.TextField(verbose_name=_("Plain Text"), validators=[validate_template])
    html_content = models.TextField(verbose_name=_("HTML"), validators=[validate_template])

    EDITOR_REVIEW_NOTICE = "Editor Review Notice"
    EDITOR_REVIEW_REMINDER = "Editor Review Reminder"
    STUDENT_REMINDER = "Student Reminder"
    PUBLISHING_NOTICE_CONTRIBUTOR = "Publishing Notice Contributor"
    PUBLISHING_NOTICE_PARTICIPANT = "Publishing Notice Participant"
    LOGIN_KEY_CREATED = "Login Key Created"
    EVALUATION_STARTED = "Evaluation Started"
    DIRECT_DELEGATION = "Direct Delegation"
    TEXT_ANSWER_REVIEW_REMINDER = "Text Answer Review Reminder"

    class Recipients(models.TextChoices):
        ALL_PARTICIPANTS = "all_participants", _("all participants")
        DUE_PARTICIPANTS = "due_participants", _("due participants")
        RESPONSIBLE = "responsible", _("responsible person")
        EDITORS = "editors", _("all editors")
        CONTRIBUTORS = "contributors", _("all contributors")

    @classmethod
    def recipient_list_for_evaluation(cls, evaluation, recipient_groups, filter_users_in_cc):
        recipients = set()

        if (
            cls.Recipients.CONTRIBUTORS in recipient_groups
            or cls.Recipients.EDITORS in recipient_groups
            or cls.Recipients.RESPONSIBLE in recipient_groups
        ):
            recipients.update(evaluation.course.responsibles.all())
            if cls.Recipients.CONTRIBUTORS in recipient_groups:
                recipients.update(UserProfile.objects.filter(contributions__evaluation=evaluation))
            elif cls.Recipients.EDITORS in recipient_groups:
                recipients.update(
                    UserProfile.objects.filter(
                        contributions__evaluation=evaluation,
                        contributions__role=Contribution.Role.EDITOR,
                    )
                )

        if cls.Recipients.ALL_PARTICIPANTS in recipient_groups:
            recipients.update(evaluation.participants.all())
        elif cls.Recipients.DUE_PARTICIPANTS in recipient_groups:
            recipients.update(evaluation.due_participants)

        if filter_users_in_cc:
            # remove delegates and CC users of recipients from the recipient list
            # so they won't get the exact same email twice
            users_excluded = UserProfile.objects.filter(
                Q(represented_users__in=recipients) | Q(ccing_users__in=recipients)
            )
            # but do so only if they have no delegates/cc_users, because otherwise
            # those won't get the email at all. consequently, some "edge case users"
            # will get the email twice, but there is no satisfying way around that.
            users_excluded = users_excluded.filter(delegates=None, cc_users=None)

            recipients = recipients - set(users_excluded)

        return list(recipients)

    @staticmethod
    def render_string(text, dictionary, *, autoescape=True):
        result = Template(text).render(Context(dictionary, autoescape))

        # Template.render would return a SafeData instance. If we didn't escape, this should not be marked as safe.
        if not autoescape:
            result = result + ""
            assert not isinstance(result, SafeData)

        return result

    def send_to_users_in_evaluations(self, evaluations, recipient_groups, use_cc, request):
        user_evaluation_map = {}
        for evaluation in evaluations:
            recipients = self.recipient_list_for_evaluation(evaluation, recipient_groups, filter_users_in_cc=use_cc)
            for user in recipients:
                user_evaluation_map.setdefault(user, []).append(evaluation)

        for user, user_evaluations in user_evaluation_map.items():
            subject_params = {}
            evaluations_with_date = {}
            for evaluation in user_evaluations:
                evaluations_with_date[evaluation] = (evaluation.vote_end_date - date.today()).days
            evaluations_with_date = sorted(evaluations_with_date.items(), key=lambda tup: tup[0].full_name)
            body_params = {
                "user": user,
                "evaluations": evaluations_with_date,
                "due_evaluations": user.get_sorted_due_evaluations(),
            }
            self.send_to_user(user, subject_params, body_params, use_cc=use_cc, request=request)

    def send_to_user(self, user, subject_params, body_params, use_cc, additional_cc_users=(), request=None):
        if not user.email:
            warning_message = (
                f"{user.full_name_with_additional_info} has no email address defined. Could not send email."
            )
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
        body_params["login_url"] = ""
        if user.needs_login_key:
            user.ensure_valid_login_key()
            if not cc_addresses:
                body_params["login_url"] = user.login_url
            else:
                send_separate_login_url = True

        body_params["page_url"] = settings.PAGE_URL
        body_params["contact_email"] = settings.CONTACT_EMAIL

        mail = self.construct_mail(user.email, cc_addresses, subject_params, body_params)

        try:
            mail.send(False)
            logger.info('Sent email "%s" to %s.', mail.subject, user.full_name_with_additional_info)
            if send_separate_login_url:
                self.send_login_url_to_user(user)
        except Exception:  # pylint: disable=broad-except
            logger.exception(
                'An exception occurred when sending the following email to user "%s":\n%s\n',
                user.full_name_with_additional_info,
                mail.message(),
            )

    def construct_mail(self, to_email, cc_addresses, subject_params, body_params):
        subject = self.render_string(self.subject, subject_params, autoescape=False)
        plain_content = self.render_string(self.plain_content, body_params, autoescape=False)

        html_content = self.html_content if self.html_content else linebreaksbr(self.plain_content)
        rendered_content = self.render_string(html_content, body_params)
        wrapper_template_params = {"email_content": rendered_content, "email_subject": subject, **body_params}
        wrapped_content = render_to_string("email_base.html", wrapper_template_params)

        mail = EmailMultiAlternatives(
            subject=subject,
            body=plain_content,
            to=[to_email],
            cc=cc_addresses,
            bcc=[a[1] for a in settings.MANAGERS],
            headers={"Reply-To": settings.REPLY_TO_EMAIL},
            alternatives=[(wrapped_content, "text/html")],
        )

        return mail

    @classmethod
    def send_reminder_to_user(cls, user, first_due_in_days, due_evaluations):
        template = cls.objects.get(name=cls.STUDENT_REMINDER)
        subject_params = {"user": user, "first_due_in_days": first_due_in_days}
        body_params = {"user": user, "first_due_in_days": first_due_in_days, "due_evaluations": due_evaluations}

        template.send_to_user(user, subject_params, body_params, use_cc=False)

    @classmethod
    def send_login_url_to_user(cls, user):
        template = cls.objects.get(name=cls.LOGIN_KEY_CREATED)
        subject_params = {}
        body_params = {"user": user}

        template.send_to_user(user, subject_params, body_params, use_cc=False)
        logger.info("Sent login url to %s.", user.email)

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
            body_params = {"user": contributor, "evaluations": evaluation_set}
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
            body_params = {"user": participant, "evaluations": evaluation_set}
            template.send_to_user(participant, {}, body_params, use_cc=True)

    @classmethod
    def send_textanswer_reminder_to_user(cls, user: UserProfile, evaluation_url_tuples: list[tuple[Evaluation, str]]):
        body_params = {"user": user, "evaluation_url_tuples": evaluation_url_tuples}
        template = cls.objects.get(name=cls.TEXT_ANSWER_REVIEW_REMINDER)
        template.send_to_user(user, {}, body_params, use_cc=False)


class VoteTimestamp(models.Model):
    evaluation = models.ForeignKey(Evaluation, models.CASCADE)
    timestamp = models.DateTimeField(verbose_name=_("vote timestamp"), default=now)
