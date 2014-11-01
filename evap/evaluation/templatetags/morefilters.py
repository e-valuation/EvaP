from django import template
from django.conf import settings
from django.template import Library
from evap.evaluation.tools import LIKERT_NAMES, GRADE_NAMES, STATES_ORDERED, STUDENT_STATES_ORDERED
from evap.rewards.tools import can_user_use_reward_points

register = Library()


# from http://www.jongales.com/blog/2009/10/19/percentage-django-template-tag/
@register.filter(name='percentage')
def percentage(fraction, population):
    try:
        return "%.0f%%" % ((float(fraction) / float(population)) * 100)
    except ValueError:
        return None
    except ZeroDivisionError:
        return None


@register.filter(name='likertname')
def likertname(grade):
    return LIKERT_NAMES.get(grade)


@register.filter(name='gradename')
def gradename(grade):
    return GRADE_NAMES.get(grade)


@register.filter(name='statename')
def statename(state):
    return STATES_ORDERED.get(state)


@register.filter(name='studentstatename')
def studentstatename(state):
    return STUDENT_STATES_ORDERED.get(state)


@register.filter(name='can_user_see_course')
def can_user_see_course(course, user):
    return course.can_user_see_results(user)


@register.filter(name='can_user_use_reward_points')
def can_use_reward_points(user):
    return can_user_use_reward_points(user)


@register.tag
def value_from_settings(parser, token):
    try:
        # split_contents() knows not to split quoted strings.
        tag_name, var = token.split_contents()
    except ValueError:
        raise template.TemplateSyntaxError("%r tag requires a single argument" % token.contents.split()[0])
    return ValueFromSettings(var)


class ValueFromSettings(template.Node):
    def __init__(self, var):
        super(ValueFromSettings, self).__init__()
        self.arg = template.Variable(var)

    def render(self, context):
        return settings.__getattr__(str(self.arg))
