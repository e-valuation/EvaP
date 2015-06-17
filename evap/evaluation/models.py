from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import EmailMessage
from django.db import models
from django.db.models import Count
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils.translation import ugettext_lazy as _
from django.utils.functional import cached_property
from django.template.base import TemplateSyntaxError, TemplateEncodingError
from django.template import Context, Template
from django_fsm import FSMField, transition
import django.dispatch
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin, Group

# see evaluation.meta for the use of Translate in this file
from evap.evaluation.meta import LocalizeModelBase, Translate

import datetime
import random

# for converting state into student_state
STUDENT_STATES_NAMES = {
    'new': 'upcoming',
    'prepared': 'upcoming',
    'editorApproved': 'upcoming',
    'approved': 'upcoming',
    'inEvaluation': 'inEvaluation',
    'evaluated': 'evaluationFinished',
    'reviewed': 'evaluationFinished',
    'published': 'published'
}

class NotArchiveable(Exception):
    """An attempt has been made to archive something that is not archiveable."""
    pass


class Semester(models.Model, metaclass=LocalizeModelBase):
    """Represents a semester, e.g. the winter term of 2011/2012."""

    name_de = models.CharField(max_length=1024, unique=True, verbose_name=_("name (german)"))
    name_en = models.CharField(max_length=1024, unique=True, verbose_name=_("name (english)"))

    name = Translate

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
        return all(course.is_archiveable for course in self.course_set.all())

    @cached_property
    def is_archived(self):
        if self.course_set.count() == 0:
            return False
        first_course_is_archived = self.course_set.first().is_archived
        assert(all(course.is_archived == first_course_is_archived for course in self.course_set.all()))
        return first_course_is_archived

    def archive(self):
        if not self.is_archiveable:
            raise NotArchiveable()
        for course in self.course_set.all():
            course._archive()

    @classmethod
    def get_all_with_published_courses(cls):
        return cls.objects.filter(course__state="published").distinct()

    @classmethod
    def active_semester(cls):
        return cls.objects.order_by("created_at").last()


class Questionnaire(models.Model, metaclass=LocalizeModelBase):
    """A named collection of questions."""

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

    index = models.IntegerField(verbose_name=_("ordering index"), default=0)

    is_for_contributors = models.BooleanField(verbose_name=_("is for contributors"), default=False)
    obsolete = models.BooleanField(verbose_name=_("obsolete"), default=False)

    class Meta:
        ordering = ('index', 'name_de')
        verbose_name = _("questionnaire")
        verbose_name_plural = _("questionnaires")

    def __str__(self):
        return self.name

    @property
    def can_staff_edit(self):
        return not self.contributions.exists()

    @property
    def can_staff_delete(self):
        return self.can_staff_edit

    @property
    def text_questions(self):
        return [question for question in self.question_set.all() if question.is_text_question]

    @property
    def rating_questions(self):
        return [question for question in self.question_set.all() if question.is_rating_question]

    SINGLE_RESULT_QUESTIONNAIRE_NAME = "Single result"

    @classmethod
    def get_single_result_questionnaire(cls):
        return cls.objects.get(name_en=cls.SINGLE_RESULT_QUESTIONNAIRE_NAME)


class Degree(models.Model, metaclass=LocalizeModelBase):
    name_de = models.CharField(max_length=1024, verbose_name=_("name (german)"), unique=True)
    name_en = models.CharField(max_length=1024, verbose_name=_("name (english)"), unique=True)
    name = Translate

    order = models.IntegerField(verbose_name=_("degree order"), default=0)

    class Meta:
        ordering = ['order', ]

    def __str__(self):
        return self.name


class Course(models.Model, metaclass=LocalizeModelBase):
    """Models a single course, e.g. the Math 101 course of 2002."""

    state = FSMField(default='new', protected=True)

    semester = models.ForeignKey(Semester, verbose_name=_("semester"))

    name_de = models.CharField(max_length=1024, verbose_name=_("name (german)"))
    name_en = models.CharField(max_length=1024, verbose_name=_("name (english)"))
    name = Translate

    # type of course: lecture, seminar, project
    type = models.CharField(max_length=1024, verbose_name=_("type"))

    # e.g. Bachelor, Master
    degrees = models.ManyToManyField(Degree, verbose_name=_("degrees"))

    # default is True as that's the more restrictive option
    is_graded = models.BooleanField(verbose_name=_("is graded"), default=True)

    # whether participants must vote to qualify for reward points
    is_required_for_reward = models.BooleanField(verbose_name=_("is required for reward"), default=True)

    # students that are allowed to vote
    participants = models.ManyToManyField(settings.AUTH_USER_MODEL, verbose_name=_("participants"), blank=True)
    _participant_count = models.IntegerField(verbose_name=_("participant count"), blank=True, null=True, default=None)

    # students that already voted
    voters = models.ManyToManyField(settings.AUTH_USER_MODEL, verbose_name=_("voters"), blank=True, related_name='+')
    _voter_count = models.IntegerField(verbose_name=_("voter count"), blank=True, null=True, default=None)

    # when the evaluation takes place
    vote_start_date = models.DateField(verbose_name=_("first day of evaluation"))
    vote_end_date = models.DateField(verbose_name=_("last day of evaluation"))

    # who last modified this course
    last_modified_time = models.DateTimeField(auto_now=True)
    last_modified_user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="+", null=True, blank=True, on_delete=models.SET_NULL)

    course_evaluated = django.dispatch.Signal(providing_args=['request', 'semester'])

    class Meta:
        ordering = ('semester', 'name_de')
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
            self.general_contribution = self.contributions.create(contributor=None)

    def is_fully_reviewed(self):
        return not self.open_textanswer_set.exists()

    def is_not_fully_reviewed(self):
        return self.open_textanswer_set.exists()

    def is_in_evaluation_period(self):
        today = datetime.date.today()
        return today >= self.vote_start_date and today <= self.vote_end_date

    def has_enough_questionnaires(self):
        return self.general_contribution and all(self.contributions.aggregate(Count('questionnaires')).values())

    def can_user_vote(self, user):
        """Returns whether the user is allowed to vote on this course."""
        return (self.state == "inEvaluation"
            and self.is_in_evaluation_period
            and user in self.participants.all()
            and user not in self.voters.all())

    def can_user_see_results(self, user):
        if user.is_staff:
            return True
        if self.state == 'published':
            return self.can_publish_grades or self.is_user_contributor_or_delegate(user)
        return False

    def is_single_result(self):
        # early return to save some queries
        if self.vote_start_date != self.vote_end_date:
            return False

        return self.contributions.get(responsible=True).questionnaires.filter(name_en=Questionnaire.SINGLE_RESULT_QUESTIONNAIRE_NAME).exists()

    @property
    def can_staff_edit(self):
        return not self.is_archived and self.state in ['new', 'prepared', 'editorApproved', 'approved', 'inEvaluation', 'evaluated', 'reviewed']

    @property
    def can_staff_delete(self):
        return self.can_staff_edit and not self.num_voters > 0

    @property
    def can_staff_approve(self):
        return self.state in ['new', 'prepared', 'editorApproved']

    @property
    def can_publish_grades(self):
        from evap.evaluation.tools import get_sum_of_answer_counters
        if self.is_single_result():
            return get_sum_of_answer_counters(self.gradeanswer_counters) > 0

        return self.num_voters >= settings.MIN_ANSWER_COUNT and float(self.num_voters) / self.num_participants >= settings.MIN_ANSWER_PERCENTAGE

    @transition(field=state, source=['new', 'editorApproved'], target='prepared')
    def ready_for_contributors(self):
        pass

    @transition(field=state, source='prepared', target='editorApproved')
    def contributor_approve(self):
        pass

    @transition(field=state, source=['new', 'prepared', 'editorApproved'], target='approved', conditions=[has_enough_questionnaires])
    def staff_approve(self):
        pass

    @transition(field=state, source='prepared', target='new')
    def revert_to_new(self):
        pass

    @transition(field=state, source='approved', target='inEvaluation', conditions=[is_in_evaluation_period])
    def evaluation_begin(self):
        pass

    @transition(field=state, source=['evaluated', 'reviewed'], target='inEvaluation', conditions=[is_in_evaluation_period])
    def reopen_evaluation(self):
        pass

    @transition(field=state, source='inEvaluation', target='evaluated')
    def evaluation_end(self):
        pass

    @transition(field=state, source='evaluated', target='reviewed', conditions=[is_fully_reviewed])
    def review_finished(self):
        pass

    @transition(field=state, source=['new', 'reviewed'], target='reviewed', conditions=[is_single_result])
    def single_result_created(self):
        pass

    @transition(field=state, source='reviewed', target='evaluated', conditions=[is_not_fully_reviewed])
    def reopen_review(self):
        pass

    @transition(field=state, source='reviewed', target='published')
    def publish(self):
        pass

    @transition(field=state, source='published', target='reviewed')
    def unpublish(self):
        pass

    @property
    def student_state(self):
        return STUDENT_STATES_NAMES[self.state]

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
    def responsible_contributor(self):
        return self.contributions.get(responsible=True).contributor

    @property
    def days_left_for_evaluation(self):
        return (self.vote_end_date - datetime.date.today()).days

    def is_user_editor_or_delegate(self, user):
        if self.contributions.filter(can_edit=True, contributor=user).exists():
            return True
        else:
            represented_users = user.represented_users.all()
            if self.contributions.filter(can_edit=True, contributor__in=represented_users).exists():
                return True

        return False

    def is_user_responsible_or_delegate(self, user):
        if self.contributions.filter(responsible=True, contributor=user).exists():
            return True
        else:
            represented_users = user.represented_users.all()
            if self.contributions.filter(responsible=True, contributor__in=represented_users).exists():
                return True

        return False

    def is_user_contributor(self, user):
        return self.contributions.filter(contributor=user).exists()

    def is_user_contributor_or_delegate(self, user):
        if self.is_user_contributor(user):
            return True
        else:
            represented_users = user.represented_users.all()
            if self.contributions.filter(contributor__in=represented_users).exists():
                return True
        return False

    def is_user_editor(self, user):
        return self.contributions.filter(contributor=user, can_edit=True).exists()

    def warnings(self):
        result = []
        if self.state in ['new', 'prepared', 'editorApproved'] and not self.has_enough_questionnaires() and not self.is_single_result():
            result.append(_("Not enough questionnaires assigned"))
        if self.state in ['inEvaluation', 'evaluated', 'reviewed', 'published'] and not self.can_publish_grades:
            result.append(_("Not enough participants to publish results"))
        return result

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
    def likertanswer_counters(self):
        """Pseudo relationship to all Likert answers for this course"""
        return LikertAnswerCounter.objects.filter(contribution__course=self)

    @property
    def gradeanswer_counters(self):
        """Pseudo relationship to all grade answers for this course"""
        return GradeAnswerCounter.objects.filter(contribution__course=self)

    def _archive(self):
        """Should be called only via Semester.archive"""
        if not self.is_archiveable:
            raise NotArchiveable()
        self._participant_count = self.participants.count()
        self._voter_count = self.voters.count()
        self.save()

    @property
    def is_archived(self):
        assert((self._participant_count is None) == (self._voter_count is None))
        return self._participant_count is not None

    @property
    def is_archiveable(self):
        return not self.is_archived and self.state in ["new", "published"]

    def was_evaluated(self, request):
        self.course_evaluated.send(sender=self.__class__, request=request, semester=self.semester)

    @property
    def final_grade_documents(self):
        from evap.grades.models import GradeDocument
        return self.grade_documents.filter(type=GradeDocument.FINAL_GRADES)

    @property
    def preliminary_grade_documents(self):
        from evap.grades.models import GradeDocument
        return self.grade_documents.exclude(type=GradeDocument.FINAL_GRADES)
    


class Contribution(models.Model):
    """A contributor who is assigned to a course and his questionnaires."""

    course = models.ForeignKey(Course, verbose_name=_("course"), related_name='contributions')
    contributor = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name=_("contributor"), blank=True, null=True, related_name='contributions')
    questionnaires = models.ManyToManyField(Questionnaire, verbose_name=_("questionnaires"), blank=True, related_name="contributions")
    responsible = models.BooleanField(verbose_name=_("responsible"), default=False)
    can_edit = models.BooleanField(verbose_name=_("can edit"), default=False)

    order = models.IntegerField(verbose_name=_("contribution order"), default=-1)

    class Meta:
        unique_together = (
            ('course', 'contributor'),
        )
        ordering = ['order', ]

    def clean(self):
        # responsible contributors can always edit
        if self.responsible:
            self.can_edit = True

    @property
    def is_general(self):
        return self.contributor == None


class Question(models.Model, metaclass=LocalizeModelBase):
    """A question including a type."""

    QUESTION_TYPES = (
        ("T", _("Text Question")),
        ("L", _("Likert Question")),
        ("G", _("Grade Question")),
    )

    questionnaire = models.ForeignKey(Questionnaire)
    text_de = models.TextField(verbose_name=_("question text (german)"))
    text_en = models.TextField(verbose_name=_("question text (english)"))
    type = models.CharField(max_length=1, choices=QUESTION_TYPES, verbose_name=_("question type"))

    text = Translate

    class Meta:
        order_with_respect_to = 'questionnaire'
        verbose_name = _("question")
        verbose_name_plural = _("questions")

    @property
    def answer_class(self):
        if self.type == "T":
            return TextAnswer
        elif self.type == "L":
            return LikertAnswerCounter
        elif self.type == "G":
            return GradeAnswerCounter
        else:
            raise Exception("Unknown answer type: %r" % self.type)

    @property
    def is_likert_question(self):
        return self.answer_class == LikertAnswerCounter

    @property
    def is_text_question(self):
        return self.answer_class == TextAnswer

    @property
    def is_grade_question(self):
        return self.answer_class == GradeAnswerCounter

    @property
    def is_rating_question(self):
        return self.is_grade_question or self.is_likert_question


class Answer(models.Model):
    """An abstract answer to a question. For anonymity purposes, the answering
    user ist not stored in the object. Concrete subclasses are `LikertAnswerCounter`,
    `TextAnswer` and `GradeAnswerCounter`."""

    question = models.ForeignKey(Question)
    contribution = models.ForeignKey(Contribution, related_name="%(class)s_set")

    class Meta:
        abstract = True
        verbose_name = _("answer")
        verbose_name_plural = _("answers")


class LikertAnswerCounter(Answer):
    """A Likert-scale answer counter to a question with answer `1` being *strongly agree*
    and `5` being *strongly disagree*."""

    answer = models.IntegerField(verbose_name=_("answer"))
    count = models.IntegerField(verbose_name=_("count"), default=0)

    class Meta:
        unique_together = (
            ('question', 'contribution', 'answer'),
        )
        verbose_name = _("Likert answer")
        verbose_name_plural = _("Likert answers")

    def add_vote(self):
        self.count += 1


class GradeAnswerCounter(Answer):
    """A grade answer counter to a question with answer `1` being best and `5` being worst."""

    answer = models.IntegerField(verbose_name=_("answer"))
    count = models.IntegerField(verbose_name=_("count"), default=0)

    class Meta:
        unique_together = (
            ('question', 'contribution', 'answer'),
        )
        verbose_name = _("grade answer")
        verbose_name_plural = _("grade answers")

    def add_vote(self):
        self.count += 1


class TextAnswer(Answer):
    """A free-form text answer to a question (usually a comment about a course
    or a contributor)."""

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
        verbose_name = _("text answer")
        verbose_name_plural = _("text answers")

    @property
    def is_reviewed(self):
        return self.state != self.NOT_REVIEWED
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

    title_de = models.TextField(verbose_name=_("section title (german)"))
    title_en = models.TextField(verbose_name=_("section title (english)"))
    title = Translate

    class Meta:
        ordering = ['order', ]
        verbose_name = _("section")
        verbose_name_plural = _("sections")


class FaqQuestion(models.Model, metaclass=LocalizeModelBase):
    """Question and answer in the frequently asked questions"""

    section = models.ForeignKey(FaqSection, related_name="questions")

    order = models.IntegerField(verbose_name=_("question order"), default=-1)

    question_de = models.TextField(verbose_name=_("question (german)"))
    question_en = models.TextField(verbose_name=_("question (english)"))
    question = Translate

    answer_de = models.TextField(verbose_name=_("answer (german)"))
    answer_en = models.TextField(verbose_name=_("answer (german)"))
    answer = Translate

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
            email=email,
            first_name=first_name,
            last_name=last_name
        )
        user.is_superuser = True
        user.save()
        user.groups.add(Group.objects.get(name="Staff"))
        return user


# taken from http://stackoverflow.com/questions/454436/unique-fields-that-allow-nulls-in-django
# and https://docs.djangoproject.com/en/1.8/howto/custom-model-fields/#converting-values-to-python-objects
class EmailNullField(models.EmailField):

    description = "EmailField that stores NULL but returns ''"

    def from_db_value(self, value, expression, connection, context):
        return value or ""

    def to_python(self, value):  # this is the value right out of the db, or an instance
        return value or ""

    def get_prep_value(self, value):  # catches value right before sending to db
        return value or None


class UserProfile(AbstractBaseUser, PermissionsMixin):
    username = models.CharField(max_length=255, unique=True, verbose_name=_('username'))
    email = EmailNullField(max_length=255, unique=True, blank=True, null=True, verbose_name=_('email address'))
    title = models.CharField(max_length=255, blank=True, null=True, verbose_name=_("Title"))
    first_name = models.CharField(max_length=255, blank=True, null=True, verbose_name=_("first name"))
    last_name = models.CharField(max_length=255, blank=True, null=True, verbose_name=_("last name"))

    # delegates of the user, which can also manage their courses
    delegates = models.ManyToManyField("UserProfile", verbose_name=_("Delegates"), related_name="represented_users", blank=True)

    # users to which all emails should be sent in cc without giving them delegate rights
    cc_users = models.ManyToManyField("UserProfile", verbose_name=_("CC Users"), related_name="ccing_users", blank=True)

    # key for url based login of this user
    MAX_LOGIN_KEY = 2**31-1

    login_key = models.IntegerField(verbose_name=_("Login Key"), unique=True, blank=True, null=True)
    login_key_valid_until = models.DateField(verbose_name=_("Login Key Validity"), blank=True, null=True)

    class Meta:
        ordering = ('last_name', 'first_name', 'username')
        verbose_name = _('user')
        verbose_name_plural = _('users')


    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = []

    objects = UserProfileManager()

    # needed e.g. for compatibility with contrib.auth.admin
    def get_full_name(self):
        return self.full_name

    # needed e.g. for compatibility with contrib.auth.admin
    def get_short_name(self):
        if self.first_name:
            return self.first_name
        return self.username

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

    def __str__(self):
        return self.full_name;

    @property
    def is_active(self):
        return True

    @property
    def is_staff(self):
        return self.groups.filter(name='Staff').exists()

    @property
    def is_grade_publisher(self):
        return self.groups.filter(name='Grade publisher').exists()

    @property
    def can_staff_delete(self):
        states_with_votes = ["inEvaluation", "reviewed", "evaluated", "published"]
        if any(course.state in states_with_votes and not course.is_archived for course in self.course_set.all()):
            return False
        return not self.is_contributor

    @property
    def is_participant(self):
        return self.course_set.exists()

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

    def generate_login_key(self):
        while True:
            key = random.randrange(0, UserProfile.MAX_LOGIN_KEY)
            if not UserProfile.objects.filter(login_key=key).exists():
                # key not yet used
                self.login_key = key
                break
        self.refresh_login_key()

    def refresh_login_key(self):
        self.login_key_valid_until = datetime.date.today() + datetime.timedelta(settings.LOGIN_KEY_VALIDITY)

def validate_template(value):
    """Field validator which ensures that the value can be compiled into a
    Django Template."""
    try:
        Template(value)
    except (TemplateSyntaxError, TemplateEncodingError) as e:
        raise ValidationError(str(e))


class EmailTemplate(models.Model):
    name = models.CharField(max_length=1024, unique=True, verbose_name=_("Name"))

    subject = models.CharField(max_length=1024, verbose_name=_("Subject"), validators=[validate_template])
    body = models.TextField(verbose_name=_("Body"), validators=[validate_template])

    @classmethod
    def get_review_template(cls):
        return cls.objects.get(name="Editor Review Notice")

    @classmethod
    def get_reminder_template(cls):
        return cls.objects.get(name="Student Reminder")

    @classmethod
    def get_publish_template(cls):
        return cls.objects.get(name="Publishing Notice")

    @classmethod
    def get_login_key_template(cls):
        return cls.objects.get(name="Login Key Created")

    @classmethod
    def get_evaluation_started_template(cls):
        return cls.objects.get(name="Evaluation Started")

    @classmethod
    def recipient_list_for_course(cls, course, recipient_groups):
        recipients = []

        if "responsible" in recipient_groups:
            recipients += [course.responsible_contributor]

        if "contributors" in recipient_groups:
            recipients += [c.contributor for c in course.contributions.exclude(contributor=None)]
        elif "editors" in recipient_groups:
            recipients += [c.contributor for c in course.contributions.exclude(contributor=None).filter(can_edit=True)]

        if "all_participants" in recipient_groups:
            recipients += course.participants.all()
        elif "due_participants" in recipient_groups:
            recipients += course.due_participants

        return recipients

    @classmethod
    def render_string(cls, text, dictionary):
        return Template(text).render(Context(dictionary, autoescape=False))

    def send_to_users_in_courses(self, courses, recipient_groups):
        user_course_map = {}
        for course in courses:
            responsible = course.responsible_contributor
            for user in self.recipient_list_for_course(course, recipient_groups):
                if user.email and user not in responsible.cc_users.all() and user not in responsible.delegates.all():
                    user_course_map.setdefault(user, []).append(course)

        for user, courses in user_course_map.items():
            self.send_to_user(user, courses)

    def send_to_user(self, user, courses=None, cc=True):
        if not user.email:
            return

        if cc:
            cc_users = set(user.delegates.all() | user.cc_users.all())
            cc_addresses = [p.email for p in cc_users if p.email]
        else:
            cc_addresses = []

        mail = EmailMessage(
            subject = self.render_string(self.subject, {'user': user, 'courses': courses}),
            body = self.render_string(self.body, {'user': user, 'courses': courses}),
            to = [user.email],
            cc = cc_addresses,
            bcc = [a[1] for a in settings.MANAGERS],
            headers = {'Reply-To': settings.REPLY_TO_EMAIL})
        mail.send(False)

    @classmethod
    def send_reminder_to_user(cls, user, due_in_number_of_days, due_courses):
        if not user.email:
            return

        template = cls.get_reminder_template()
        subject = template.render_string(template.subject, {'user': user, 'due_in_number_of_days': due_in_number_of_days})
        body = template.render_string(template.body, {'user': user, 'due_in_number_of_days': due_in_number_of_days, 'due_courses': due_courses})

        mail = EmailMessage(
            subject = subject,
            body = body,
            to = [user.email],
            bcc = [a[1] for a in settings.MANAGERS],
            headers = {'Reply-To': settings.REPLY_TO_EMAIL})
        mail.send(False)
