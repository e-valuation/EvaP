from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils.translation import ugettext_lazy as _

from django_fsm.db.fields import FSMField, transition

# see evaluation.meta for the use of Translate in this file
from evap.evaluation.meta import LocalizeModelBase, Translate

from evap.fsr.models import EmailTemplate

import datetime
import random
import sys


class Semester(models.Model):
    """Represents a semester, e.g. the winter term of 2011/2012."""
    
    __metaclass__ = LocalizeModelBase
    
    name_de = models.CharField(max_length=100, unique=True, verbose_name=_(u"name (german)"))
    name_en = models.CharField(max_length=100, unique=True, verbose_name=_(u"name (english)"))
    
    name = Translate
    
    created_at = models.DateField(verbose_name=_(u"created at"), auto_now_add=True)
    
    class Meta:
        ordering = ('-created_at', 'name_de')
        verbose_name = _(u"semester")
        verbose_name_plural = _(u"semesters")
    
    def __unicode__(self):
        return self.name
    
    @property
    def can_fsr_delete(self):
        for course in self.course_set.all():
            if not course.can_fsr_delete:
                return False
        return True
        
    @classmethod
    def get_all_with_published_courses(cls):
        return cls.objects.filter(course__state="published").distinct()


class Questionnaire(models.Model):
    """A named collection of questions."""
    
    __metaclass__ = LocalizeModelBase
    
    name_de = models.CharField(max_length=100, unique=True, verbose_name=_(u"name (german)"))
    name_en = models.CharField(max_length=100, unique=True, verbose_name=_(u"name (english)"))
    name = Translate
    
    description_de = models.TextField(verbose_name=_(u"description (german)"), blank=True, null=True)
    description_en = models.TextField(verbose_name=_(u"description (english)"), blank=True, null=True)
    description = Translate
    
    public_name_de = models.CharField(max_length=100, verbose_name=_(u"public name (german)"))
    public_name_en = models.CharField(max_length=100, verbose_name=_(u"public name (english)"))
    public_name = Translate
    
    teaser_de = models.TextField(verbose_name=_(u"teaser (german)"), blank=True, null=True)
    teaser_en = models.TextField(verbose_name=_(u"teaser (english)"), blank=True, null=True)
    teaser = Translate
    
    index = models.IntegerField(verbose_name=_(u"ordering index"))
    
    is_for_persons = models.BooleanField(verbose_name=_(u"is for persons"))
    obsolete = models.BooleanField(verbose_name=_(u"obsolete"), default=False)
    
    class Meta:
        ordering = ('obsolete', 'index', 'name_de')
        verbose_name = _(u"questionnaire")
        verbose_name_plural = _(u"questionnaires")
    
    def __unicode__(self):
        return self.name
    
    @property
    def can_fsr_delete(self):
        return not self.assigned_to.exists()


class Course(models.Model):
    """Models a single course, e.g. the Math 101 course of 2002."""
    
    __metaclass__ = LocalizeModelBase
    
    state = FSMField(default='new', protected=True)

    semester = models.ForeignKey(Semester, verbose_name=_(u"semester"))
    
    name_de = models.CharField(max_length=140, verbose_name=_(u"name (german)"))
    name_en = models.CharField(max_length=140, verbose_name=_(u"name (english)"))
    name = Translate
    
    # type of course: lecture, seminar, project
    kind = models.CharField(max_length=100, verbose_name=_(u"type"))
    
    # bachelor, master, d-school course
    degree = models.CharField(max_length=100, verbose_name=_(u"degree"))
    
    # students that are allowed to vote
    participants = models.ManyToManyField(settings.AUTH_USER_MODEL, verbose_name=_(u"participants"), blank=True)
    participant_count = models.IntegerField(verbose_name=_(u"participant count"), blank=True, null=True, default=None)
    
    # students that already voted
    voters = models.ManyToManyField(settings.AUTH_USER_MODEL, verbose_name=_(u"voters"), blank=True, related_name='+')
    voter_count = models.IntegerField(verbose_name=_(u"voter count"), blank=True, null=True, default=None)
    
    # when the evaluation takes place
    vote_start_date = models.DateField(null=True, verbose_name=_(u"first date to vote"))
    vote_end_date = models.DateField(null=True, verbose_name=_(u"last date to vote"))
    
    # who last modified this course, shell be noted
    last_modified_time = models.DateTimeField(auto_now=True)
    last_modified_user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="+", null=True, blank=True)

    class Meta:
        ordering = ('semester', 'degree', 'name_de')
        unique_together = (
            ('semester', 'degree', 'name_de'),
            ('semester', 'degree', 'name_en'),
        )
        verbose_name = _(u"course")
        verbose_name_plural = _(u"courses")
    
    def __unicode__(self):
        return self.name
    
    def clean(self):
        if not (self.vote_start_date < self.vote_end_date):
            raise ValidationError(_(u"The vote start date must be before the vote end date."))
    
    def save(self, *args, **kw):
        super(Course, self).save(*args, **kw)
        
        # make sure there is a general assignment
        if not self.general_assignment:
            self.assignments.create(lecturer=None)
    
    def is_fully_checked(self):
        """Shortcut for finding out whether all text answers to this course have been checked"""
        return not self.textanswer_set.filter(checked=False).exists()
    
    def can_user_vote(self, user):
        """Returns whether the user is allowed to vote on this course."""
        if (not self.state == "inEvaluation") or (self.vote_end_date < datetime.date.today()):
            return False
        
        return user in self.participants.all() and user not in self.voters.all()
    
    def can_fsr_edit(self):
        return self.state in ['new', 'prepared', 'lecturerApproved', 'approved', 'inEvaluation']
    
    def can_fsr_delete(self):
        return not (self.textanswer_set.exists() or self.gradeanswer_set.exists() or not self.can_fsr_edit())
    
    def can_fsr_review(self):
        return (not self.is_fully_checked()) and self.state in ['inEvaluation', 'evaluated']
    
    def can_fsr_approve(self):
        return self.state in ['new', 'prepared', 'lecturerApproved']
        
    def has_lecturer(self):
        for assignment in self.assignments.all():
            if assignment.lecturer:
                if UserProfile.get_for_user(assignment.lecturer).is_lecturer:
                    return True
        return False
    
    @transition(field=state, source=['new', 'lecturerApproved'], target='prepared')
    def ready_for_lecturer(self, send_mail=True):
        if send_mail:
            EmailTemplate.get_review_template().send_courses([self], True, False)
    
    @transition(field=state, source='prepared', target='lecturerApproved')
    def lecturer_approve(self):
        pass
    
    @transition(field=state, source=['new', 'prepared', 'lecturerApproved'], target='approved')
    def fsr_approve(self):
        pass
    
    @transition(field=state, source='approved', target='inEvaluation')
    def evaluation_begin(self):
        pass
    
    @transition(field=state, source='inEvaluation', target='evaluated')
    def evaluation_end(self):
        pass
    
    @transition(field=state, source='evaluated', target='reviewed', conditions=[is_fully_checked])
    def review_finished(self):
        pass
    
    @transition(field=state, source='reviewed', target='published')
    def publish(self):
        pass
    
    @transition(field=state, source='published', target='reviewed')
    def revoke(self):
        pass

    @property
    def general_assignment(self):
        try:
            return self.assignments.get(lecturer=None)
        except Assignment.DoesNotExist:
            return None
    
    @property
    def num_participants(self):
        if self.participants.exists():
            return self.participants.count()
        else:
            return self.participant_count or 0
    
    @property
    def num_voters(self):
        if self.voters.exists():
            return self.voters.count()
        else:
            return self.voter_count or 0

    @property
    def first_lecturer(self):
        for assignment in self.assignments.exclude(lecturer=None):
            if UserProfile.get_for_user(assignment.lecturer).is_lecturer:
                return assignment.lecturer
        return None

    
    def has_enough_questionnaires(self):
        return all(assignment.questionnaires.exists() for assignment in self.assignments.all()) and self.general_assignment
    
    def is_user_lecturer(self, user):
        if self.assignments.filter(lecturer=user).exists() and UserProfile.get_for_user(user).is_lecturer:
            return True
        elif self.assignments.filter(lecturer__in=user.represented_users.all()).exists():
            return True
        
        return False
    
    def is_user_lecturer_or_ta(self, user):
        if self.assignments.filter(lecturer=user).exists():
            return True
        elif self.assignments.filter(lecturer__in=user.represented_users.all()).exists():
            return True
        
        return False
    
    def warnings(self):
        result = []
        if not self.assignments.exclude(lecturer=None).exists():
            result.append(_(u"No lecturers assigned"))
        if not self.has_enough_questionnaires():
            result.append(_(u"Not enough questionnaires assigned"))
        if not self.has_lecturer():
            result.append(_(u"Managing lecturer missing"))
        return result
    
    @property
    def textanswer_set(self):
        """Pseudo relationship to all text answers for this course"""
        return TextAnswer.objects.filter(assignment__in=self.assignments.all())

    @property
    def open_textanswer_set(self):
        """Pseudo relationship to all text answers for this course"""
        return TextAnswer.objects.filter(assignment__in=self.assignments.all()).filter(checked=False)
    
    @property
    def checked_textanswer_set(self):
        """Pseudo relationship to all text answers for this course"""
        return TextAnswer.objects.filter(assignment__in=self.assignments.all()).filter(checked=True)
    
    @property
    def gradeanswer_set(self):
        """Pseudo relationship to all grade answers for this course"""
        return GradeAnswer.objects.filter(assignment__in=self.assignments.all())


class Assignment(models.Model):
    """A lecturer who is assigned to a course and his questionnaires."""
    
    course = models.ForeignKey(Course, verbose_name=_(u"course"), related_name='assignments')
    lecturer = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name=_(u"lecturer"), blank=True, null=True, related_name='lecturers')
    questionnaires = models.ManyToManyField(Questionnaire, verbose_name=_(u"questionnaires"),
                                            blank=True, related_name="assigned_to")
    read_only = models.BooleanField(verbose_name=_("read-only"))

    class Meta:
        unique_together = (
            ('course', 'lecturer'),
        )


class Question(models.Model):
    """A question including a type."""
    
    __metaclass__ = LocalizeModelBase
    
    QUESTION_KINDS = (
        (u"T", _(u"Text Question")),
        (u"G", _(u"Grade Question"))
    )
    
    questionnaire = models.ForeignKey(Questionnaire)
    text_de = models.TextField(verbose_name=_(u"question text (german)"))
    text_en = models.TextField(verbose_name=_(u"question text (english)"))
    kind = models.CharField(max_length=1, choices=QUESTION_KINDS,
                            verbose_name=_(u"kind of question"))
    
    text = Translate
    
    class Meta:
        order_with_respect_to = 'questionnaire'
        verbose_name = _(u"question")
        verbose_name_plural = _(u"questions")
    
    @property
    def answer_class(self):
        if self.kind == u"T":
            return TextAnswer
        elif self.kind == u"G":
            return GradeAnswer
        else:
            raise Exception("Unknown answer kind: %r" % self.kind)
    
    def is_grade_question(self):
        return self.answer_class == GradeAnswer
    
    def is_text_question(self):
        return self.answer_class == TextAnswer


class Answer(models.Model):
    """An abstract answer to a question. For anonymity purposes, the answering
    user ist not stored in the object. Concrete subclasses are `GradeAnswer` and
    `TextAnswer`."""
    
    question = models.ForeignKey(Question)
    assignment = models.ForeignKey(Assignment)
    
    class Meta:
        abstract = True
        verbose_name = _(u"answer")
        verbose_name_plural = _(u"answers")


class GradeAnswer(Answer):
    """A Likert-scale answer to a question with `1` being *strongly agree* and `5`
    being *strongly disagree*."""
    
    answer = models.IntegerField(verbose_name=_(u"answer"))
    
    class Meta:
        verbose_name = _(u"grade answer")
        verbose_name_plural = _(u"grade answers")


class TextAnswer(Answer):
    """A free-form text answer to a question (usually a comment about a course
    or a lecturer)."""
    
    elements_per_page = 5
    
    reviewed_answer = models.TextField(verbose_name=_(u"reviewed answer"), blank=True, null=True)
    original_answer = models.TextField(verbose_name=_(u"original answer"), blank=True)
    
    checked = models.BooleanField(verbose_name=_(u"answer checked"))
    hidden = models.BooleanField(verbose_name=_(u"hide answer"))
    
    class Meta:
        verbose_name = _(u"text answer")
        verbose_name_plural = _(u"text answers")
    
    def _answer_get(self):
        return self.reviewed_answer or self.original_answer
    
    def _answer_set(self, value):
        self.original_answer = value
        self.reviewed_answer = None
    
    answer = property(_answer_get, _answer_set)


class UserProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL)
    
    # extending first_name and last_name from the user
    title = models.CharField(verbose_name=_(u"Title"), max_length=30, blank=True, null=True)
    
    # picture of the user
    picture = models.ImageField(verbose_name=_(u"Picture"), upload_to="pictures", blank=True, null=True)
    
    # delegates of the user, which can also manage their courses
    delegates = models.ManyToManyField(settings.AUTH_USER_MODEL, verbose_name=_(u"Delegates"), related_name="represented_users", blank=True)
    
    # is the user possibly a lecturer
    is_lecturer = models.BooleanField(verbose_name=_(u"Lecturer"))
    
    # key for url based logon of this user
    MAX_LOGON_KEY = 2**31-1

    logon_key = models.IntegerField(verbose_name=_(u"Logon Key"), blank=True, null=True)
    logon_key_valid_until = models.DateField(verbose_name=_(u"Login Key Validity"), null=True)
    
    class Meta:
        verbose_name = _('user')
        verbose_name_plural = _('users')
    
    def __unicode__(self):
        return unicode(self.user)
    
    @property
    def full_name(self):
        if self.user.last_name:
            name = self.user.last_name
            if self.user.first_name:
                name = self.user.first_name + " " + name
            if self.title:
                name = self.title + " " + name
            return name
        else:
            return self.user.username
    
    @property
    def can_fsr_delete(self):
        return not Course.objects.filter(assignments__lecturer=self.user).exists()
    
    def has_courses(self):
        return Course.objects.exclude(voters__pk=self.user.id).filter(participants__pk=self.user.id).exists()
    
    def is_lecturer_or_delegate(self):
        return self.is_lecturer or UserProfile.objects.filter(delegates=self.user, is_lecturer=True).exists()
    
    @classmethod
    def get_for_user(cls, user):
        obj, _ = cls.objects.get_or_create(user=user)
        return obj
    
    def generate_logon_key(self):
        while True:
            key = random.randrange(0, UserProfile.MAX_LOGON_KEY)
            if not UserProfile.objects.filter(logon_key=key).exists():
                # key not yet used
                self.logon_key = key
                break
        
        self.logon_key_valid_until = datetime.date.today() + datetime.timedelta(settings.LOGIN_KEY_VALIDITY)
    
    @staticmethod
    @receiver(post_save, sender=settings.AUTH_USER_MODEL)
    def create_user_profile(sender, instance, created, **kwargs):
        """Creates a UserProfile object whenever a User is created."""
        if created:
            UserProfile.objects.create(user=instance)

# disable super user creation on syncdb
from django.db.models import signals
from django.contrib.auth.management import create_superuser
from django.contrib.auth import models as auth_app


signals.post_syncdb.disconnect(
    create_superuser,
    sender=auth_app,
    dispatch_uid="django.contrib.auth.management.create_superuser")
