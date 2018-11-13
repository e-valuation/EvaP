from django.template import Library

from evap.evaluation.models import CHOICES
from evap.evaluation.tools import STATES_ORDERED, STATE_DESCRIPTIONS
from evap.rewards.tools import can_user_use_reward_points


register = Library()


@register.filter(name='zip')
def _zip(a, b):
    return zip(a, b)


@register.filter
def ordering_index(course):
    if course.state in ['new', 'prepared', 'editor_approved', 'approved']:
        return course.days_until_evaluation
    elif course.state == "in_evaluation":
        return 100000 + course.days_left_for_evaluation
    else:
        return 200000 + course.days_left_for_evaluation


# from http://www.jongales.com/blog/2009/10/19/percentage-django-template-tag/
@register.filter
def percentage(fraction, population):
    try:
        return "{0:.0f}%".format(int(float(fraction) / float(population) * 100))
    except ValueError:
        return None
    except ZeroDivisionError:
        return None


@register.filter
def percentage_one_decimal(fraction, population):
    try:
        return "{0:.1f}%".format((float(fraction) / float(population)) * 100)
    except ValueError:
        return None
    except ZeroDivisionError:
        return None


@register.filter
def percentage_value(fraction, population):
    try:
        return "{0:0f}".format((float(fraction) / float(population)) * 100)
    except ValueError:
        return None
    except ZeroDivisionError:
        return None


@register.filter
def get_answer_name(question, grade):
    choices = CHOICES[question.type]
    try:
        idx = choices.grades.index(grade)
        return choices.names[idx]
    except (IndexError, ValueError):
        return None


@register.filter
def statename(state):
    return STATES_ORDERED.get(state)


@register.filter
def statedescription(state):
    return STATE_DESCRIPTIONS.get(state)


@register.filter
def can_user_see_results_page(course, user):
    return course.can_user_see_results_page(user)


@register.filter(name='can_user_use_reward_points')
def _can_user_use_reward_points(user):
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


@register.filter
def hours_and_minutes(time_left_for_evaluation):
    hours = time_left_for_evaluation.seconds // 3600
    minutes = (time_left_for_evaluation.seconds // 60) % 60
    return "{:02}:{:02}".format(hours, minutes)


@register.filter
def has_nonresponsible_editor(course):
    return course.contributions.filter(responsible=False, can_edit=True).exists()
