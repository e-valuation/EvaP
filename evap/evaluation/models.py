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
        for key in classDict.keys():
            if classDict[key] is Translate:
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
    
    def __unicode__(self):
        return self.name
    
    @classmethod
    def current(cls):
        return cls.objects.all().reverse()[0]
    
    class Meta:
        verbose_name = _(u"semester")
        verbose_name_plural = _(u"semesters")


class Course(models.Model):
    """Models a single course, e.g. the Math 101 course of 2002."""
    
    __metaclass__ = LocalizeModelBase

    semester = models.ForeignKey(Semester, verbose_name=_(u"semester"))
    name_de = models.CharField(max_length=100, verbose_name=_(u"name (german)"))
    name_en = models.CharField(max_length=100, verbose_name=_(u"name (english)"))
    
    name = Translate
    
    # students that are allowed to vote
    participants = models.ManyToManyField(User, verbose_name=_(u"participants"),
                                          blank=True)
    # students that already voted
    voters = models.ManyToManyField(User, verbose_name=_(u"voters"), blank=True,
                                    related_name='+')
    
    vote_start_date = models.DateField(null=True, verbose_name=_(u"first date to vote"))
    vote_end_date = models.DateField(null=True, verbose_name=_(u"last date to vote"))
    
    publish_date = models.DateField(null=True, verbose_name=_(u"publishing date"))
    
    def can_user_vote(self, user):
        return user in self.participants.all() and not user in self.voters.all()
    
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
    
    class Meta:
        verbose_name = _(u"course")
        verbose_name_plural = _(u"courses")


class QuestionGroup(models.Model):
    """A named collection of questions."""
    
    __metaclass__ = LocalizeModelBase
    
    name_de = models.CharField(max_length=100, verbose_name=_(u"name (german)"))
    name_en = models.CharField(max_length=100, verbose_name=_(u"name (english)"))
    
    name = Translate
    
    def __unicode__(self):
        return self.name
    
    class Meta:
        verbose_name = _(u"question group")
        verbose_name_plural = _(u"question groups")


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



class Questionnaire(models.Model):
    """A questionnaire connects a course and optionally a lecturer to a question group."""
    
    course = models.ForeignKey(Course, verbose_name=_(u"course"))
    question_group = models.ForeignKey(QuestionGroup, verbose_name=_(u"question group"))
    
    def __unicode__(self):
        return u"%s: %s" % (self.course.name, self.question_group.name)
    
    def questions(self):
        """Shortcut method to retrieve all questions"""
        return self.question_group.question_set.all()
    
    class Meta:
        verbose_name = _(u"questionnaire")
        verbose_name_plural = _(u"questionnaires")


class Answer(models.Model):
    """An answer to a question. For anonymity purposes, the answering user
    ist not stored in the answer."""
    
    question = models.ForeignKey(Question)
    questionnaire = models.ForeignKey(Questionnaire)
    
    class Meta:
        verbose_name = _(u"answer")
        verbose_name_plural = _(u"answers")
        
        abstract = True


class GradeAnswer(Answer):
    answer = models.IntegerField(verbose_name = _(u"answer"))


class TextAnswer(Answer):
    answer = models.TextField(verbose_name = _(u"answer"))

