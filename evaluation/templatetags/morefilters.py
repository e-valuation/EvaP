from django.template import Library
from evap.evaluation.tools import LIKERT_NAMES, GRADE_NAMES, STATES_ORDERED, STATE_DESCRIPTIONS, STUDENT_STATES_ORDERED, \
                                    get_grade_color, get_deviation_color
from evap.rewards.tools import can_user_use_reward_points

register = Library()


@register.filter(name='zip')
def zip_lists(a, b):
    return zip(a, b)


@register.filter(name='gradecolor')
def gradecolor(grade):
    return 'rgb({}, {}, {})'.format(*get_grade_color(grade))


@register.filter(name='deviationcolor')
def deviationcolor(deviation):
    return 'rgb({}, {}, {})'.format(*get_deviation_color(deviation))


# from http://www.jongales.com/blog/2009/10/19/percentage-django-template-tag/
@register.filter(name='percentage')
def percentage(fraction, population):
    try:
        return "{0:.0f}%".format((float(fraction) / float(population)) * 100)
    except ValueError:
        return None
    except ZeroDivisionError:
        return None


@register.filter(name='percentage_one_decimal')
def percentage_one_decimal(fraction, population):
    try:
        return "{0:.1f}%".format((float(fraction) / float(population)) * 100)
    except ValueError:
        return None
    except ZeroDivisionError:
        return None


@register.filter(name='percentage_value')
def percentage_value(fraction, population):
    try:
        return "{0:0f}".format((float(fraction) / float(population)) * 100)
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


@register.filter(name='statedescription')
def statedescription(state):
    return STATE_DESCRIPTIONS.get(state)


@register.filter(name='studentstatename')
def studentstatename(state):
    return STUDENT_STATES_ORDERED.get(state)


@register.filter(name='can_user_see_results')
def can_user_see_results(course, user):
    return course.can_user_see_results(user)


@register.filter(name='can_user_use_reward_points')
def can_use_reward_points(user):
    return can_user_use_reward_points(user)


@register.filter
def is_choice_field(field):
    return field.field.__class__.__name__ == "TypedChoiceField"


@register.filter
def is_user_editor_or_delegate(course, user):
    return course.is_user_editor_or_delegate(user)
