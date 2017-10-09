from django.template import Library
from evap.evaluation.tools import POSITIVE_YES_NO_NAMES, NEGATIVE_YES_NO_NAMES, LIKERT_NAMES, STATE_DESCRIPTIONS, STATES_ORDERED, STUDENT_STATES_ORDERED
from evap.rewards.tools import can_user_use_reward_points

register = Library()


@register.filter(name='zip')
def zip_lists(a, b):
    return zip(a, b)


# from http://www.jongales.com/blog/2009/10/19/percentage-django-template-tag/
@register.filter(name='percentage')
def percentage(fraction, population):
    try:
        return "{0:.0f}%".format(int(float(fraction) / float(population) * 100))
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


@register.filter(name='get_answer_name')
def get_answer_name(question, grade):
    if question.is_likert_question:
        return LIKERT_NAMES.get(grade)
    elif question.is_positive_yes_no_question:
        return POSITIVE_YES_NO_NAMES.get(grade)
    elif question.is_negative_yes_no_question:
        return NEGATIVE_YES_NO_NAMES.get(grade)
    else:
        return grade


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


@register.filter(name='can_publish_grades')
def can_publish_grades(course):
    return course.can_publish_grades


@register.filter(name='can_user_use_reward_points')
def can_use_reward_points(user):
    return can_user_use_reward_points(user)


@register.filter
def is_choice_field(field):
    return field.field.__class__.__name__ == "TypedChoiceField"


@register.filter
def is_heading_field(field):
    return field.field.__class__.__name__ == "HeadingField"


@register.filter
def is_user_editor_or_delegate(course, user):
    return course.is_user_editor_or_delegate(user)


@register.filter
def message_class(level):
    return {
        'debug': 'info',
        'info': 'info',
        'success': 'success',
        'warning': 'warning',
        'error': 'danger',
    }.get(level, 'info')
