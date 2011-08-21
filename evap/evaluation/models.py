from django.db import models
from django.db.models.base import ModelBase
from django.contrib.auth.models import User
from django.utils.translation import ugettext_lazy as _
from django.utils.translation import get_language
from datetime import datetime

Translate = object()

class LocalizeModelBase(ModelBase):
    """This meta-class provides automatically translated content properties. Set
    a model field to `Translate` and it will automatically return the property
    with the name of the current language. E.g. if there is a normal member
    `text_de`, a member `text = Translate` and the current language is `de`, then
    an object will return the content of `text_de` when it is asked for the value
    of `text`.
    """
    def __new__(metacls, classname, bases, classDict):
        # find all classDict entries that point to `Translate`
        for key in classDict.keys():
            if classDict[key] is Translate:
                # replace them with a getter that uses the current language
                def make_property(k):
                    return property(lambda self: getattr(self, "%s_%s" % (k, get_language())))
                classDict[key] = make_property(key)
        return super(LocalizeModelBase, metacls).__new__(metacls, classname, bases, classDict)


class Semester(models.Model):
    """Represents a semester, e.g. the winter term of 2011/2012."""
    
    __metaclass__ = LocalizeModelBase
    
    name_de = models.CharField(max_length=100, verbose_name=_(u"name (german)"))
    name_en = models.CharField(max_length=100, verbose_name=_(u"name (english)"))
    
    name = Translate
    
    visible = models.BooleanField(verbose_name=_(u"visible"), default=False)
    created_at = models.DateField(verbose_name=_(u"created at"), auto_now_add=True)
    
    def __unicode__(self):
        return self.name
    
    class Meta:
        verbose_name = _(u"semester")
        verbose_name_plural = _(u"semesters")
        
        ordering = ('created_at',)


class QuestionGroup(models.Model):
    """A named collection of questions."""
    
    __metaclass__ = LocalizeModelBase
    
    name_de = models.CharField(max_length=100, unique=True, verbose_name=_(u"name (german)"))
    name_en = models.CharField(max_length=100, unique=True, verbose_name=_(u"name (english)"))
    
    name = Translate
    
    def __unicode__(self):
        return self.name
    
    class Meta:
        verbose_name = _(u"question group")
        verbose_name_plural = _(u"question groups")


class Course(models.Model):
    """Models a single course, e.g. the Math 101 course of 2002."""
    
    __metaclass__ = LocalizeModelBase

    semester = models.ForeignKey(Semester, verbose_name=_(u"semester"))
    name_de = models.CharField(max_length=100, verbose_name=_(u"name (german)"))
    name_en = models.CharField(max_length=100, verbose_name=_(u"name (english)"))
    
    name = Translate
    
    # type of course: lecture, seminar, project
    kind = models.CharField(max_length=100, verbose_name=_(u"type"))
    
    # students that are allowed to vote
    participants = models.ManyToManyField(User, verbose_name=_(u"participants"), blank=True)
    
    # students that already voted
    voters = models.ManyToManyField(User, verbose_name=_(u"voters"), blank=True, related_name='+')
    
    primary_lecturers = models.ManyToManyField(User, verbose_name=_(u"primary lecturers"), blank=True, related_name='primary_courses')
    secondary_lecturers = models.ManyToManyField(User, verbose_name=_(u"secondary lecturers"), blank=True, related_name='secondary_courses')
    
    # different kinds of question_groups
    general_questions = models.ManyToManyField(QuestionGroup, blank=True, verbose_name=_("course question groups"), related_name="general_courses")
    primary_lecturer_questions = models.ManyToManyField(QuestionGroup, blank=True, verbose_name=_("primary lecturer question groups"), related_name="primary_courses")
    secondary_lecturer_questions = models.ManyToManyField(QuestionGroup, blank=True, verbose_name=_("secondary lecturer question groups"), related_name="secondary_courses")
    
    vote_start_date = models.DateField(null=True, verbose_name=_(u"first date to vote"))
    vote_end_date = models.DateField(null=True, verbose_name=_(u"last date to vote"))
    
    publish_date = models.DateField(null=True, verbose_name=_(u"publishing date"))
    
    class Meta:
        verbose_name = _(u"course")
        verbose_name_plural = _(u"courses")
        
        ordering = ('semester', 'name_de')
    
    def can_user_vote(self, user):
        return user in self.participants.all() and user not in self.voters.all()
        
    def voted_percentage(self):
        if self.participants.count() == 0:
            return '-'
        return ((self.voters.count()*1.0) / self.participants.count()) * 100.0
    
    @property
    def textanswer_set(self):
        """Pseudo relationship to all text answers for this course"""
        return TextAnswer.objects.filter(course=self)
    
    def fully_checked(self):
        """Shortcut for finding out whether all textanswers to this course have been checked"""
        return self.textanswer_set.filter(checked=False).count() == 0
    
    @classmethod
    def for_user(cls, user):
        """Returns a list of courses that a specific user can vote on right now"""
        return cls.objects.filter(
            vote_start_date__lte=datetime.now(),
            vote_end_date__gte=datetime.now(),
            participants=user
        ).exclude(
            voters=user
        )
    
    def __unicode__(self):
        return self.name


class Question(models.Model):
    """A question including a type."""
    
    __metaclass__ = LocalizeModelBase
    
    QUESTION_KINDS = (
        (u"T", _(u"Text Question")),
        (u"G", _(u"Grade Question"))
    )
    
    question_group = models.ForeignKey(QuestionGroup)
    text_de = models.TextField(verbose_name=_(u"question text (german)"))
    text_en = models.TextField(verbose_name=_(u"question text (english)"))
    kind = models.CharField(max_length=1, choices=QUESTION_KINDS,
                            verbose_name=_(u"kind of question"))
    
    text = Translate
    
    class Meta:
        verbose_name = _(u"question")
        verbose_name_plural = _(u"questions")
        
        order_with_respect_to = 'question_group'
    
    def answer_class(self):
        if self.kind == u"T":
            return TextAnswer
        elif self.kind == u"G":
            return GradeAnswer
        else:
            raise Exception("Unknown answer kind: %r" % self.kind)
    
    def is_text_question(self):
        return self.answer_class() == TextAnswer
    
    def is_grade_question(self):
        return self.answer_class() == GradeAnswer


class Answer(models.Model):
    """An abstract answer to a question. For anonymity purposes, the answering
    user ist not stored in the object. Concrete subclasses are `GradeAnswer` and
    `TextAnswer`."""
    
    question = models.ForeignKey(Question)
    course = models.ForeignKey(Course, related_name="+")
    lecturer = models.ForeignKey(User, related_name="+", blank=True, null=True, on_delete=models.SET_NULL)
    
    class Meta:
        verbose_name = _(u"answer")
        verbose_name_plural = _(u"answers")
        
        abstract = True


class GradeAnswer(Answer):
    answer = models.IntegerField(verbose_name = _(u"answer"))
    
    class Meta:
        verbose_name = _(u"grade answer")
        verbose_name_plural = _(u"grade answers")


class TextAnswer(Answer):
    censored_answer = models.TextField(verbose_name = _(u"censored answer"), blank=True, null=True)
    original_answer = models.TextField(verbose_name = _(u"original answer"), blank=True)
    
    checked = models.BooleanField(verbose_name = _(u"answer checked"))
    hidden = models.BooleanField(verbose_name = _(u"hide answer"))
    
    class Meta:
        verbose_name = _(u"text answer")
        verbose_name_plural = _(u"text answers")
    
    def _answer_get(self):
        return self.censored_answer or self.original_answer
    
    def _answer_set(self, value):
        self.original_answer = value
        self.censored_answer = None
    
    answer = property(_answer_get, _answer_set)
