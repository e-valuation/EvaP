from django.db import models
from django.contrib.auth.models import User
from django.utils.translation import ugettext_lazy as _
from django.utils.translation import get_language
from datetime import datetime

class AutoLocalizeMixin(object):
    def __getattr__(self, name):
        localized_name = "%s_%s" % (name, get_language())
        if hasattr(self, localized_name):
            return getattr(self, localized_name)
        return getattr(super(AutoLocalizeMixin, self), name)


class Semester(models.Model, AutoLocalizeMixin):
    name_de = models.CharField(max_length=100, verbose_name=_(u"name (german)"))
    name_en = models.CharField(max_length=100, verbose_name=_(u"name (english)"))
    
    def __unicode__(self):
        return self.name
    
    class Meta:
        verbose_name = _(u"semester")
        verbose_name_plural = _(u"semesters")


class Course(models.Model, AutoLocalizeMixin):
    """Models a single course, i.e. the Math 101 course of 2002."""

    semester = models.ForeignKey(Semester, verbose_name=_(u"semester"))
    name_de = models.CharField(max_length=100, verbose_name=_(u"name (german)"))
    name_en = models.CharField(max_length=100, verbose_name=_(u"name (english)"))
    participants = models.ManyToManyField(User, verbose_name=_(u"participants"))
    
    vote_start_date = models.DateField(null=True, verbose_name=_(u"first date to vote"))
    vote_end_date = models.DateField(null=True, verbose_name=_(u"last date to vote"))
    
    publish_date = models.DateField(null=True, verbose_name=_(u"publishing date"))
    
    @classmethod
    def for_user(cls, user):
        """Returns a list of courses that a specific user can vote on right now"""
        # FIXME: What if the user already voted?
        return cls.objects.filter(
            vote_start_date__lte=datetime.now(),
            vote_end_date__gte=datetime.now(),
            participants=user
        )
        
    def __unicode__(self):
        return self.name
    
    class Meta:
        verbose_name = _(u"course")
        verbose_name_plural = _(u"courses")


class QuestionGroup(models.Model, AutoLocalizeMixin):
    """A named collection of questions."""
    
    name_de = models.CharField(max_length=100, verbose_name=_(u"name (german)"))
    name_en = models.CharField(max_length=100, verbose_name=_(u"name (english)"))
    
    def __unicode__(self):
        return self.name
    
    class Meta:
        verbose_name = _(u"question group")
        verbose_name_plural = _(u"question groups")


class Question(models.Model, AutoLocalizeMixin):
    """A question including a type."""
    
    QUESTION_KINDS = (
        (u"T", _(u"Text Question")),
        (u"G", _(u"Grade Question"))
    )
    
    question_group = models.ForeignKey(QuestionGroup)
    text_de = models.TextField(verbose_name=_(u"question text (german)"))
    text_en = models.TextField(verbose_name=_(u"question text (english)"))
    kind = models.CharField(max_length=1, choices=QUESTION_KINDS,
                            verbose_name=_(u"kind of question"))
    
    class Meta:
        verbose_name = _(u"question")
        verbose_name_plural = _(u"questions")


class Questionnaire(models.Model):
    """A questionnaire connects a course and optionally a lecturer to a question group."""
    course = models.ForeignKey(Course, verbose_name=_(u"course"))
    question_group = models.ForeignKey(QuestionGroup, verbose_name=_(u"question group"))
    
    def __unicode__(self):
        return u"%s: %s" % (self.course.name, self.question_group.name)
    
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

