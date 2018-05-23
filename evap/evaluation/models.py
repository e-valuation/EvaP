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
from django.db import models, transaction
from django.db.models import Count, Q, Manager
from django.dispatch import Signal, receiver
from django.template import Context, Template
from django.template.base import TemplateSyntaxError
from django.utils.functional import cached_property
from django.utils.translation import ugettext_lazy as _
from django_fsm import FSMField, transition
from django_fsm.signals import post_transition
# see evaluation.meta for the use of Translate in this file
from evap.evaluation.meta import LocalizeModelBase, Translate
from evap.evaluation.tools import date_to_datetime, get_due_courses_for_user

logger = logging.getLogger(__name__)


class NotArchiveable(Exception):
    """An attempt has been made to archive something that is not archiveable."""
    pass


class Semester(models.Model, metaclass=LocalizeModelBase):
    """Represents a semester, e.g. the winter term of 2011/2012."""

    name_de = models.CharField(max_length=1024, unique=True, verbose_name=_("name (german)"))
    name_en = models.CharField(max_length=1024, unique=True, verbose_name=_("name (english)"))
    name = Translate

    is_archived = models.BooleanField(default=False, verbose_name=_("is archived"))

    created_at = models.DateField(verbose_name=_("created at"), auto_now_add=True)

    class Meta:
        ordering = ('-created_at', 'name_de')
        verbose_name = _("semester")
        verbose_name_plural = _("semesters")

    def __str__(self):
        return self.name

    @property
    def can_staff_delete(self):
        return all(course.can_staff_delete for course in self.course_set.all())

    @property
    def is_archiveable(self):
        return not self.is_archived and all(course.is_archiveable for course in self.course_set.all())

    @transaction.atomic
    def archive(self):
        if not self.is_archiveable:
            raise NotArchiveable()
        for course in self.course_set.all():
            course._archive()
        self.is_archived = True
        self.save()

    @classmethod
    def get_all_with_published_courses(cls):
        return cls.objects.filter(course__state="published").distinct()

    @classmethod
    def active_semester(cls):
        return cls.objects.order_by("created_at").last()

    @property
    def is_active_semester(self):
        return self == Semester.active_semester()


class QuestionnaireManager(Manager):
    def course_questionnaires(self):
        return super().get_queryset().exclude(type=Questionnaire.CONTRIBUTOR)

    def contributor_questionnaires(self):
        return super().get_queryset().filter(type=Questionnaire.CONTRIBUTOR)


class Questionnaire(models.Model, metaclass=LocalizeModelBase):
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
    name = Translate

    description_de = models.TextField(verbose_name=_("description (german)"), blank=True, null=True)
    description_en = models.TextField(verbose_name=_("description (english)"), blank=True, null=True)
    description = Translate

    public_name_de = models.CharField(max_length=1024, verbose_name=_("display name (german)"))
    public_name_en = models.CharField(max_length=1024, verbose_name=_("display name (english)"))
    public_name = Translate

    teaser_de = models.TextField(verbose_name=_("teaser (german)"), blank=True, null=True)
    teaser_en = models.TextField(verbose_name=_("teaser (english)"), blank=True, null=True)
    teaser = Translate

    order = models.IntegerField(verbose_name=_("ordering index"), default=0)

    staff_only = models.BooleanField(verbose_name=_("display for staff only"), default=False)
    obsolete = models.BooleanField(verbose_name=_("obsolete"), default=False)

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
    def can_staff_edit(self):
        return not self.contributions.exclude(course__state='new').exists()

    @property
    def can_staff_delete(self):
        return not self.contributions.exists()

    @property
    def text_questions(self):
        return [question for question in self.question_set.all() if question.is_text_question]

    @property
    def rating_questions(self):
        return [question for question in self.question_set.all() if question.is_rating_question]

    SINGLE_RESULT_QUESTIONNAIRE_NAME = "Single result"

    @classmethod
    def single_result_questionnaire(cls):
        return cls.objects.get(name_en=cls.SINGLE_RESULT_QUESTIONNAIRE_NAME)


class Degree(models.Model, metaclass=LocalizeModelBase):
    name_de = models.CharField(max_length=1024, verbose_name=_("name (german)"), unique=True)
    name_en = models.CharField(max_length=1024, verbose_name=_("name (english)"), unique=True)
    name = Translate

    order = models.IntegerField(verbose_name=_("degree order"), default=-1)

    class Meta:
        ordering = ['order', ]

    def __str__(self):
        return self.name

    def can_staff_delete(self):
        if self.pk is None:
            return True
        return not self.courses.all().exists()


class CourseType(models.Model, metaclass=LocalizeModelBase):
    """Model for the type of a course, e.g. a lecture"""

    name_de = models.CharField(max_length=1024, verbose_name=_("name (german)"), unique=True)
    name_en = models.CharField(max_length=1024, verbose_name=_("name (english)"), unique=True)
    name = Translate

    class Meta:
        ordering = ['name_de', ]

    def __str__(self):
        return self.name

    def __lt__(self, other):
        return self.name_de < other.name_de

    def can_staff_delete(self):
        if not self.pk:
            return True
        return not self.courses.all().exists()


class Course(models.Model, metaclass=LocalizeModelBase):
    """Models a single course, e.g. the Math 101 course of 2002."""

    state = FSMField(default='new', protected=True)

    semester = models.ForeignKey(Semester, models.PROTECT, verbose_name=_("semester"))

    name_de = models.CharField(max_length=1024, verbose_name=_("name (german)"))
    name_en = models.CharField(max_length=1024, verbose_name=_("name (english)"))
    name = Translate

    # type of course: lecture, seminar, project
    type = models.ForeignKey(CourseType, models.PROTECT, verbose_name=_("course type"), related_name="courses")

    # e.g. Bachelor, Master
    degrees = models.ManyToManyField(Degree, verbose_name=_("degrees"), related_name="courses")

    # default is True as that's the more restrictive option
    is_graded = models.BooleanField(verbose_name=_("is graded"), default=True)

    # defines whether results can only be seen by contributors and participants
    is_private = models.BooleanField(verbose_name=_("is private"), default=False)

    # graders can set this to True, then the course will be handled as if final grades have already been uploaded
    gets_no_grade_documents = models.BooleanField(verbose_name=_("gets no grade documents"), default=False)

    # whether participants must vote to qualify for reward points
    is_rewarded = models.BooleanField(verbose_name=_("is rewarded"), default=True)

    # whether the evaluation does take place during the semester, stating that evaluation results will be published while the course is still running
    is_midterm_evaluation = models.BooleanField(verbose_name=_("is midterm evaluation"), default=False)

    # students that are allowed to vote
    participants = models.ManyToManyField(settings.AUTH_USER_MODEL, verbose_name=_("participants"), blank=True, related_name='courses_participating_in')
    _participant_count = models.IntegerField(verbose_name=_("participant count"), blank=True, null=True, default=None)

    # students that already voted
    voters = models.ManyToManyField(settings.AUTH_USER_MODEL, verbose_name=_("voters"), blank=True, related_name='courses_voted_for')
    _voter_count = models.IntegerField(verbose_name=_("voter count"), blank=True, null=True, default=None)

    # when the evaluation takes place
    vote_start_datetime = models.DateTimeField(verbose_name=_("start of evaluation"))
    vote_end_date = models.DateField(verbose_name=_("last day of evaluation"))

    # who last modified this course
    last_modified_time = models.DateTimeField(auto_now=True)
    last_modified_user = models.ForeignKey(settings.AUTH_USER_MODEL, models.SET_NULL, null=True, blank=True, related_name="course_last_modified_user+")

    course_evaluated = Signal(providing_args=['request', 'semester'])

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

    def save(self, *args, **kw):
        super().save(*args, **kw)

        # make sure there is a general contribution
        if not self.general_contribution:
            self.contributions.create(contributor=None)
            del self.general_contribution  # invalidate cached property

        assert self.vote_end_date >= self.vote_start_datetime.date()

    @property
    def is_fully_reviewed(self):
        return not self.open_textanswer_set.exists()

    @property
    def vote_end_datetime(self):
        # The evaluation ends at EVALUATION_END_OFFSET_HOURS:00 of the day AFTER self.vote_end_date.
        return date_to_datetime(self.vote_end_date) + timedelta(hours=24 + settings.EVALUATION_END_OFFSET_HOURS)

    @property
    def is_in_evaluation_period(self):
        now = datetime.now()

        return self.vote_start_datetime <= now <= self.vote_end_datetime

    @property
    def general_contribution_has_questionnaires(self):
        return self.general_contribution and (self.is_single_result or self.general_contribution.questionnaires.count() > 0)

    @property
    def all_contributions_have_questionnaires(self):
        return self.general_contribution and (self.is_single_result or all(self.contributions.annotate(Count('questionnaires')).values_list("questionnaires__count", flat=True)))

    def can_user_vote(self, user):
        """Returns whether the user is allowed to vote on this course."""
        return (self.state == "in_evaluation"
            and self.is_in_evaluation_period
            and user in self.participants.all()
            and user not in self.voters.all())

    def can_user_see_course(self, user):
        if user.is_reviewer:
            return True
        if self.is_user_contributor_or_delegate(user):
            return True
        if user in self.participants.all():
            return True
        if self.is_private:
            return False
        if user.is_external:
            return False
        return True

    def can_user_see_results_page(self, user):
        if user.is_reviewer:
            return True
        if self.state == 'published':
            if self.is_user_contributor_or_delegate(user):
                return True
            if not self.has_enough_voters_to_publish_grades:
                return False
            return self.can_user_see_course(user)
        return False

    def can_user_see_grades(self, user):
        if user.is_reviewer:
            return True
        if self.state != 'published':
            return False
        if not self.has_enough_voters_to_publish_grades:
            return False
        return self.can_user_see_course(user)

    @property
    def is_single_result(self):
        # early return to save some queries
        if self.vote_start_datetime.date() != self.vote_end_date:
            return False

        return self.contributions.filter(responsible=True, questionnaires__name_en=Questionnaire.SINGLE_RESULT_QUESTIONNAIRE_NAME).exists()

    @property
    def can_staff_edit(self):
        return not self.is_archived and self.state in ['new', 'prepared', 'editor_approved', 'approved', 'in_evaluation', 'evaluated', 'reviewed']

    @property
    def can_staff_delete(self):
        return self.can_staff_edit and (not self.num_voters > 0 or self.is_single_result)

    @property
    def has_enough_voters_to_publish_grades(self):
        from evap.results.tools import get_sum_of_answer_counters
        if self.is_single_result:
            return get_sum_of_answer_counters(self.ratinganswer_counters) > 0

        return (self.num_voters >= settings.VOTER_COUNT_NEEDED_FOR_PUBLISHING
                and float(self.num_voters) / self.num_participants >= settings.VOTER_PERCENTAGE_NEEDED_FOR_PUBLISHING)

    @transition(field=state, source=['new', 'editor_approved'], target='prepared')
    def ready_for_editors(self):
        pass

    @transition(field=state, source='prepared', target='editor_approved')
    def editor_approve(self):
        pass

    @transition(field=state, source=['new', 'prepared', 'editor_approved'], target='approved', conditions=[lambda self: self.general_contribution_has_questionnaires])
    def staff_approve(self):
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
        pass

    @transition(field=state, source='published', target='reviewed')
    def unpublish(self):
        from evap.results.tools import get_results_cache_key
        caches['results'].delete(get_results_cache_key(self))

    @cached_property
    def general_contribution(self):
        try:
            return self.contributions.get(contributor=None)
        except Contribution.DoesNotExist:
            return None

    @cached_property
    def num_participants(self):
        if self._participant_count is not None:
            return self._participant_count
        return self.participants.count()

    @cached_property
    def num_voters(self):
        if self._voter_count is not None:
            return self._voter_count
        return self.voters.count()

    @property
    def due_participants(self):
        return self.participants.exclude(pk__in=self.voters.all())

    @cached_property
    def responsible_contributors(self):
        return UserProfile.objects.filter(contributions__course=self, contributions__responsible=True).order_by('contributions__order')

    @cached_property
    def num_contributors(self):
        return UserProfile.objects.filter(contributions__course=self).count()

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
        if self.contributions.filter(can_edit=True, contributor=user).exists():
            return True
        represented_users = user.represented_users.all()
        if self.contributions.filter(can_edit=True, contributor__in=represented_users).exists():
            return True
        return False

    def is_user_contributor_or_delegate(self, user):
        if self.contributions.filter(contributor=user).exists():
            return True
        represented_users = user.represented_users.all()
        if self.contributions.filter(contributor__in=represented_users).exists():
            return True
        return False

    @property
    def textanswer_set(self):
        """Pseudo relationship to all text answers for this course"""
        return TextAnswer.objects.filter(contribution__course=self)

    @cached_property
    def num_textanswers(self):
        return self.textanswer_set.count()

    @property
    def open_textanswer_set(self):
        """Pseudo relationship to all text answers for this course"""
        return self.textanswer_set.filter(state=TextAnswer.NOT_REVIEWED)

    @property
    def reviewed_textanswer_set(self):
        """Pseudo relationship to all text answers for this course"""
        return self.textanswer_set.exclude(state=TextAnswer.NOT_REVIEWED)

    @cached_property
    def num_reviewed_textanswers(self):
        return self.reviewed_textanswer_set.count()

    @property
    def ratinganswer_counters(self):
        """Pseudo relationship to all rating answers for this course"""
        return RatingAnswerCounter.objects.filter(contribution__course=self)

    def _archive(self):
        """Should be called only via Semester.archive"""
        if not self.is_archiveable:
            raise NotArchiveable()
        self._participant_count = self.num_participants
        self._voter_count = self.num_voters
        self.save()

    @property
    def is_archived(self):
        semester_is_archived = self.semester.is_archived
        if semester_is_archived:
            assert self._participant_count is not None and self._voter_count is not None
        return semester_is_archived

    @property
    def is_archiveable(self):
        return not self.is_archived and self.state in ["new", "published"]

    @property
    def final_grade_documents(self):
        from evap.grades.models import GradeDocument
        return self.grade_documents.filter(type=GradeDocument.FINAL_GRADES)

    @property
    def midterm_grade_documents(self):
        from evap.grades.models import GradeDocument
        return self.grade_documents.filter(type=GradeDocument.MIDTERM_GRADES)

    @property
    def grades_activated(self):
        from evap.grades.tools import are_grades_activated
        return are_grades_activated(self.semester)

    @classmethod
    def update_courses(cls):
        logger.info("update_courses called. Processing courses now.")
        from evap.evaluation.tools import send_publish_notifications

        courses_new_in_evaluation = []
        evaluation_results_courses = []

        for course in cls.objects.all():
            try:
                if course.state == "approved" and course.vote_start_datetime <= datetime.now():
                    course.evaluation_begin()
                    course.last_modified_user = UserProfile.objects.cronjob_user()
                    course.save()
                    courses_new_in_evaluation.append(course)
                elif course.state == "in_evaluation" and datetime.now() >= course.vote_end_datetime:
                    course.evaluation_end()
                    if course.is_fully_reviewed:
                        course.review_finished()
                        if not course.is_graded or course.final_grade_documents.exists() or course.gets_no_grade_documents:
                            course.publish()
                            evaluation_results_courses.append(course)
                    course.last_modified_user = UserProfile.objects.cronjob_user()
                    course.save()
            except Exception:
                logger.exception('An error occured when updating the state of course "{}" (id {}).'.format(course, course.id))

        template = EmailTemplate.objects.get(name=EmailTemplate.EVALUATION_STARTED)
        EmailTemplate.send_to_users_in_courses(template, courses_new_in_evaluation, [EmailTemplate.ALL_PARTICIPANTS], use_cc=False, request=None)
        send_publish_notifications(evaluation_results_courses)
        logger.info("update_courses finished.")


@receiver(post_transition, sender=Course)
def log_state_transition(sender, **kwargs):
    course = kwargs['instance']
    transition_name = kwargs['name']
    source_state = kwargs['source']
    target_state = kwargs['target']
    logger.info('Course "{}" (id {}) moved from state "{}" to state "{}", caused by transition "{}".'.format(course, course.id, source_state, target_state, transition_name))


class Contribution(models.Model):
    """A contributor who is assigned to a course and his questionnaires."""

    OWN_COMMENTS = 'OWN'
    COURSE_COMMENTS = 'COURSE'
    ALL_COMMENTS = 'ALL'
    COMMENT_VISIBILITY_CHOICES = (
        (OWN_COMMENTS, _('Own')),
        (COURSE_COMMENTS, _('Course')),
        (ALL_COMMENTS, _('All')),
    )
    IS_CONTRIBUTOR = 'CONTRIBUTOR'
    IS_EDITOR = 'EDITOR'
    IS_RESPONSIBLE = 'RESPONSIBLE'
    RESPONSIBILITY_CHOICES = (
        (IS_CONTRIBUTOR, _('Contributor')),
        (IS_EDITOR, _('Editor')),
        (IS_RESPONSIBLE, _('Responsible')),
    )

    course = models.ForeignKey(Course, models.CASCADE, verbose_name=_("course"), related_name='contributions')
    contributor = models.ForeignKey(settings.AUTH_USER_MODEL, models.PROTECT, verbose_name=_("contributor"), blank=True, null=True, related_name='contributions')
    questionnaires = models.ManyToManyField(Questionnaire, verbose_name=_("questionnaires"), blank=True, related_name="contributions")
    responsible = models.BooleanField(verbose_name=_("responsible"), default=False)
    can_edit = models.BooleanField(verbose_name=_("can edit"), default=False)
    comment_visibility = models.CharField(max_length=10, choices=COMMENT_VISIBILITY_CHOICES, verbose_name=_('comment visibility'), default=OWN_COMMENTS)
    label = models.CharField(max_length=255, blank=True, null=True, verbose_name=_("label"))

    order = models.IntegerField(verbose_name=_("contribution order"), default=-1)

    class Meta:
        unique_together = (
            ('course', 'contributor'),
        )
        ordering = ['order', ]

    def save(self, *args, **kw):
        super().save(*args, **kw)
        if self.responsible and not self.course.is_single_result:
            assert self.can_edit and self.comment_visibility == self.ALL_COMMENTS

    @property
    def is_general(self):
        return self.contributor is None


class Question(models.Model, metaclass=LocalizeModelBase):
    """A question including a type."""

    QUESTION_TYPES = (
        ("T", _("Text Question")),
        ("L", _("Likert Question")),
        ("G", _("Grade Question")),
        ("P", _("Positive Yes-No Question")),
        ("N", _("Negative Yes-No Question")),
        ("H", _("Heading")),
    )

    order = models.IntegerField(verbose_name=_("question order"), default=-1)
    questionnaire = models.ForeignKey(Questionnaire, models.CASCADE)
    text_de = models.CharField(max_length=1024, verbose_name=_("question text (german)"))
    text_en = models.CharField(max_length=1024, verbose_name=_("question text (english)"))
    type = models.CharField(max_length=1, choices=QUESTION_TYPES, verbose_name=_("question type"))

    text = Translate

    class Meta:
        ordering = ['order', ]
        verbose_name = _("question")
        verbose_name_plural = _("questions")

    @property
    def answer_class(self):
        if self.is_text_question:
            return TextAnswer
        elif self.is_rating_question:
            return RatingAnswerCounter
        else:
            raise Exception("Unknown answer type: %r" % self.type)

    @property
    def is_likert_question(self):
        return self.type == "L"

    @property
    def is_text_question(self):
        return self.type == "T"

    @property
    def is_grade_question(self):
        return self.type == "G"

    @property
    def is_positive_yes_no_question(self):
        return self.type == "P"

    @property
    def is_negative_yes_no_question(self):
        return self.type == "N"

    @property
    def is_yes_no_question(self):
        return self.is_positive_yes_no_question or self.is_negative_yes_no_question

    @property
    def is_rating_question(self):
        return self.is_grade_question or self.is_likert_question or self.is_yes_no_question

    @property
    def is_non_grade_rating_question(self):
        return self.is_rating_question and not self.is_grade_question

    @property
    def is_heading_question(self):
        return self.type == "H"


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
    """A rating answer counter to a question. A lower answer is better or indicates more agreement."""

    answer = models.IntegerField(verbose_name=_("answer"))
    count = models.IntegerField(verbose_name=_("count"), default=0)

    class Meta:
        unique_together = (
            ('question', 'contribution', 'answer'),
        )
        verbose_name = _("rating answer")
        verbose_name_plural = _("rating answers")

    def add_vote(self):
        self.count += 1


class TextAnswer(Answer):
    """A free-form text answer to a question (usually a comment about a course
    or a contributor)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    reviewed_answer = models.TextField(verbose_name=_("reviewed answer"), blank=True, null=True)
    original_answer = models.TextField(verbose_name=_("original answer"), blank=True)

    HIDDEN = 'HI'
    PUBLISHED = 'PU'
    PRIVATE = 'PR'
    NOT_REVIEWED = 'NR'
    TEXT_ANSWER_STATES = (
        (HIDDEN, _('hidden')),
        (PUBLISHED, _('published')),
        (PRIVATE, _('private')),
        (NOT_REVIEWED, _('not reviewed')),
    )
    state = models.CharField(max_length=2, choices=TEXT_ANSWER_STATES, verbose_name=_('state of answer'), default=NOT_REVIEWED)

    class Meta:
        # Prevent ordering by date for privacy reasons
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
    def answer(self):
        return self.reviewed_answer or self.original_answer

    @answer.setter
    def answer(self, value):
        self.original_answer = value
        self.reviewed_answer = None

    def publish(self):
        self.state = self.PUBLISHED

    def hide(self):
        self.state = self.HIDDEN

    def make_private(self):
        self.state = self.PRIVATE

    def unreview(self):
        self.state = self.NOT_REVIEWED


class FaqSection(models.Model, metaclass=LocalizeModelBase):
    """Section in the frequently asked questions"""

    order = models.IntegerField(verbose_name=_("section order"), default=-1)

    title_de = models.CharField(max_length=255, verbose_name=_("section title (german)"))
    title_en = models.CharField(max_length=255, verbose_name=_("section title (english)"))
    title = Translate

    class Meta:
        ordering = ['order', ]
        verbose_name = _("section")
        verbose_name_plural = _("sections")


class FaqQuestion(models.Model, metaclass=LocalizeModelBase):
    """Question and answer in the frequently asked questions"""

    section = models.ForeignKey(FaqSection, models.CASCADE, related_name="questions")

    order = models.IntegerField(verbose_name=_("question order"), default=-1)

    question_de = models.CharField(max_length=1024, verbose_name=_("question (german)"))
    question_en = models.CharField(max_length=1024, verbose_name=_("question (english)"))
    question = Translate

    answer_de = models.TextField(verbose_name=_("answer (german)"))
    answer_en = models.TextField(verbose_name=_("answer (german)"))
    answer = Translate

    class Meta:
        ordering = ['order', ]
        verbose_name = _("question")
        verbose_name_plural = _("questions")


class UserProfileManager(BaseUserManager):
    def get_queryset(self):
        return super().get_queryset().exclude(username=UserProfile.CRONJOB_USER_USERNAME)

    def cronjob_user(self):
        return super().get_queryset().get(username=UserProfile.CRONJOB_USER_USERNAME)

    def exclude_inactive_users(self):
        return self.get_queryset().exclude(is_active=False)

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
            email=email,
            first_name=first_name,
            last_name=last_name
        )
        user.is_superuser = True
        user.save()
        user.groups.add(Group.objects.get(name="Staff"))
        return user


class UserProfile(AbstractBaseUser, PermissionsMixin):
    username = models.CharField(max_length=255, unique=True, verbose_name=_('username'))

    # null=True because users created through kerberos logins and certain external users don't have an address.
    email = models.EmailField(max_length=255, unique=True, blank=True, null=True, verbose_name=_('email address'))

    title = models.CharField(max_length=255, blank=True, null=True, verbose_name=_("Title"))
    first_name = models.CharField(max_length=255, blank=True, null=True, verbose_name=_("first name"))
    last_name = models.CharField(max_length=255, blank=True, null=True, verbose_name=_("last name"))

    language = models.CharField(max_length=8, blank=True, null=True, verbose_name=_("language"))

    # delegates of the user, which can also manage their courses
    delegates = models.ManyToManyField("UserProfile", verbose_name=_("Delegates"), related_name="represented_users", blank=True)

    # users to which all emails should be sent in cc without giving them delegate rights
    cc_users = models.ManyToManyField("UserProfile", verbose_name=_("CC Users"), related_name="ccing_users", blank=True)

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

    @property
    def full_name(self):
        if self.last_name:
            name = self.last_name
            if self.first_name:
                name = self.first_name + " " + name
            if self.title:
                name = self.title + " " + name
            return name
        else:
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
        return self.groups.filter(name='Staff').exists()

    @cached_property
    def is_reviewer(self):
        return self.is_staff or self.groups.filter(name='Reviewer').exists()

    @cached_property
    def is_grade_publisher(self):
        return self.groups.filter(name='Grade publisher').exists()

    CRONJOB_USER_USERNAME = "cronjob"

    @property
    def can_staff_mark_inactive(self):
        if self.is_reviewer or self.is_grade_publisher or self.is_superuser:
            return False
        if any(not course.is_archived for course in self.courses_participating_in.all()):
            return False
        if any(not contribution.course.is_archived for contribution in self.contributions.all()):
            return False
        return True

    @property
    def can_staff_delete(self):
        states_with_votes = ["in_evaluation", "reviewed", "evaluated", "published"]
        if any(course.state in states_with_votes and not course.is_archived for course in self.courses_participating_in.all()):
            return False
        if self.is_contributor or self.is_reviewer or self.is_grade_publisher or self.is_superuser:
            return False
        if any(not user.can_staff_delete for user in self.represented_users.all()):
            return False
        if any(not user.can_staff_delete for user in self.ccing_users.all()):
            return False
        return True

    @property
    def is_participant(self):
        return self.courses_participating_in.exists()

    @property
    def is_student(self):
        """
            A UserProfile is not considered to be a student anymore if the
            newest contribution is newer than the newest participation.
        """
        if not self.is_participant:
            return False

        if not self.is_contributor:
            return True

        last_semester_participated = Semester.objects.filter(course__participants=self).order_by("-created_at").first()
        last_semester_contributed = Semester.objects.filter(course__contributions__contributor=self).order_by("-created_at").first()

        return last_semester_participated.created_at >= last_semester_contributed.created_at

    @property
    def is_contributor(self):
        return self.contributions.exists()

    @property
    def is_editor(self):
        return self.contributions.filter(can_edit=True).exists()

    @property
    def is_responsible(self):
        # in the user list, self.user.contributions is prefetched, therefore use it directly and don't filter it
        return any(contribution.responsible for contribution in self.contributions.all())

    @property
    def is_delegate(self):
        return self.represented_users.exists()

    @property
    def is_editor_or_delegate(self):
        return self.is_editor or self.is_delegate

    @property
    def is_contributor_or_delegate(self):
        return self.is_contributor or self.is_delegate

    @property
    def is_external(self):
        # do the import here to prevent a circular import
        from evap.evaluation.tools import is_external_email
        if not self.email:
            return True
        return is_external_email(self.email)

    @property
    def can_download_grades(self):
        return not self.is_external

    @classmethod
    def email_needs_login_key(cls, email):
        # do the import here to prevent a circular import
        from evap.evaluation.tools import is_external_email
        return is_external_email(email)

    @property
    def needs_login_key(self):
        return UserProfile.email_needs_login_key(self.email)

    def ensure_valid_login_key(self):
        if self.login_key and self.login_key_valid_until > date.today():
            return

        while True:
            key = random.randrange(0, UserProfile.MAX_LOGIN_KEY)
            if not UserProfile.objects.filter(login_key=key).exists():
                # key not yet used
                self.login_key = key
                break
        self.refresh_login_key()

    def refresh_login_key(self):
        self.login_key_valid_until = date.today() + timedelta(settings.LOGIN_KEY_VALIDITY)
        self.save()

    @property
    def login_url(self):
        if not self.needs_login_key:
            return ""
        return settings.PAGE_URL + "?loginkey=" + str(self.login_key)

    def get_sorted_contributions(self):
        return self.contributions.order_by('course__semester__created_at', 'course__name_de')

    def get_sorted_courses_participating_in(self):
        return self.courses_participating_in.order_by('semester__created_at', 'name_de')

    def get_sorted_courses_voted_for(self):
        return self.courses_voted_for.order_by('semester__created_at', 'name_de')


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
    PUBLISHING_NOTICE = "Publishing Notice"
    LOGIN_KEY_CREATED = "Login Key Created"
    EVALUATION_STARTED = "Evaluation Started"

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
    def recipient_list_for_course(cls, course, recipient_groups, filter_users_in_cc):
        recipients = []

        if cls.CONTRIBUTORS in recipient_groups:
            recipients += UserProfile.objects.filter(contributions__course=course)
        elif cls.EDITORS in recipient_groups:
            recipients += UserProfile.objects.filter(contributions__course=course, contributions__can_edit=True)
        elif cls.RESPONSIBLE in recipient_groups:
            recipients += course.responsible_contributors

        if cls.ALL_PARTICIPANTS in recipient_groups:
            recipients += course.participants.all()
        elif cls.DUE_PARTICIPANTS in recipient_groups:
            recipients += course.due_participants

        if filter_users_in_cc:
            # remove delegates and CC users of recipients from the recipient list
            # so they won't get the exact same email twice
            users_excluded = UserProfile.objects.filter(Q(represented_users__in=recipients) | Q(ccing_users__in=recipients))
            # but do so only if they have no delegates/cc_users, because otherwise
            # those won't get the email at all. consequently, some "edge case users"
            # will get the email twice, but there is no satisfying way around that.
            users_excluded = users_excluded.filter(delegates=None, cc_users=None)

            recipients = list(set(recipients) - set(users_excluded))

        return recipients

    @classmethod
    def render_string(cls, text, dictionary):
        return Template(text).render(Context(dictionary, autoescape=False))

    @classmethod
    def send_to_users_in_courses(cls, template, courses, recipient_groups, use_cc, request):
        user_course_map = {}
        for course in courses:
            recipients = cls.recipient_list_for_course(course, recipient_groups, filter_users_in_cc=use_cc)
            for user in recipients:
                user_course_map.setdefault(user, []).append(course)

        for user, courses in user_course_map.items():
            subject_params = {}
            body_params = {'user': user, 'courses': courses, 'due_courses': get_due_courses_for_user(user)}
            cls.send_to_user(user, template, subject_params, body_params, use_cc=use_cc, request=request)

    @classmethod
    def send_to_user(cls, user, template, subject_params, body_params, use_cc, request=None):
        if not user.email:
            warning_message = "{} has no email address defined. Could not send email.".format(user.username)
            # If this method is triggered by a cronjob changing course states, the request is None.
            # In this case warnings should be sent to the admins via email (configured in the settings for logger.error).
            # If a request exists, the page is displayed in the browser and the message can be shown on the page (messages.warning).
            if request is not None:
                logger.warning(warning_message)
                messages.warning(request, _(warning_message))
            else:
                logger.error(warning_message)
            return

        if use_cc:
            cc_users = set(user.delegates.all() | user.cc_users.all())
            cc_addresses = [p.email for p in cc_users if p.email]
        else:
            cc_addresses = []

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
        except Exception:
            logger.exception('An exception occurred when sending the following email to user "{}":\n{}\n'.format(user.username, mail.message()))

    @classmethod
    def send_reminder_to_user(cls, user, first_due_in_days, due_courses):
        template = cls.objects.get(name=cls.STUDENT_REMINDER)
        subject_params = {'user': user, 'first_due_in_days': first_due_in_days}
        body_params = {'user': user, 'first_due_in_days': first_due_in_days, 'due_courses': due_courses}

        cls.send_to_user(user, template, subject_params, body_params, use_cc=False)

    @classmethod
    def send_login_url_to_user(cls, user):
        template = cls.objects.get(name=cls.LOGIN_KEY_CREATED)
        subject_params = {}
        body_params = {'user': user, 'login_url': user.login_url}

        cls.send_to_user(user, template, subject_params, body_params, use_cc=False)
        logger.info(('Sent login url to {}.').format(user.username))
