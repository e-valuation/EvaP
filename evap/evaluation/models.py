from django.db import models
from django.contrib.auth.models import User

class Semester(models.Model):
    name = models.CharField(max_length=100)


class Course(models.Model):
    """Models a single course, i.e. the Math 101 course of 2002."""

    semester = models.ForeignKey(Semester)
    name = models.CharField(max_length=100)
    participants = models.ManyToManyField(User)
    
    vote_start_date = models.DateField(null=True)
    vote_end_date = models.DateField(null=True)
    
    publish_date = models.DateField(null=True)


class QuestionGroup(models.Model):
    """A named collection of questions."""
    
    name = models.CharField(max_length=100)


class Question(models.Model):
    """A question including a type."""
    
    QUESTION_KINDS = (
        (u"T", u"Text Question"),
        (u"G", u"Grade Question")
    )
    
    question_group = models.ForeignKey(QuestionGroup)
    text = models.TextField()
    kind = models.CharField(max_length=1, choices=QUESTION_KINDS)


class Questionnaire(models.Model):
    """A questionnaire connects a course and optionally a lecturer to a question group."""
    course = models.ForeignKey(Course)
    question_group = models.ForeignKey(QuestionGroup)


class Answer(models.Model):
    """An answer to a question. For anonymity purposes, the answering user
    ist not stored in the answer."""
    
    question = models.ForeignKey(Question)
    questionnaire = models.ForeignKey(Questionnaire)
    
    class Meta:
        abstract = True


class GradeAnswer(Answer):
    answer = models.IntegerField()


class TextAnswer(Answer):
    answer = models.TextField()

