from collections import namedtuple

from django.forms import TypedChoiceField
from django.template import Library
from django.utils.translation import ugettext_lazy as _

from evap.evaluation.models import BASE_UNIPOLAR_CHOICES
from evap.rewards.tools import can_reward_points_be_used_by
from evap.student.forms import HeadingField


# the names displayed for contributors
STATE_NAMES = {
    'new': _('new'),
    'prepared': _('prepared'),
    'editor_approved': _('editor approved'),
    'approved': _('approved'),
    'in_evaluation': _('in evaluation'),
    'evaluated': _('evaluated'),
    'reviewed': _('reviewed'),
    'published': _('published'),
}


# the descriptions used in tooltips for contributors
STATE_DESCRIPTIONS = {
    'new': _('The evaluation was newly created and will be prepared by the evaluation team.'),
    'prepared': _('The evaluation was prepared by the evaluation team and is now available for editors.'),
    'editor_approved': _('The evaluation was approved by an editor and will now be checked by the evaluation team.'),
    'approved': _('All preparations are finished. The evaluation will begin once the defined start date is reached.'),
    'in_evaluation': _('The evaluation is currently running until the defined end date is reached.'),
    'evaluated': _('The evaluation has finished and will now be reviewed by the evaluation team.'),
    'reviewed': _('The evaluation has finished and was reviewed by the evaluation team. You will receive an email when its results are published.'),
    'published': _('The results for this evaluation have been published.'),
}


# values for approval states shown to staff
StateValues = namedtuple('StateValues', ('order', 'icon', 'filter', 'description'))
APPROVAL_STATES = {
    'new': StateValues(0, 'fas fa-circle icon-yellow', 'fa-circle icon-yellow', _('In preparation')),
    'prepared': StateValues(2, 'far fa-square icon-gray', 'fa-square icon-gray', _('Awaiting editor review')),
    'editor_approved': StateValues(1, 'far fa-check-square icon-yellow', 'fa-check-square icon-yellow', _('Approved by editor, awaiting manager review')),
    'approved': StateValues(3, 'far fa-check-square icon-green', 'fa-check-square icon-green', _('Approved by manager')),
}


register = Library()


@register.filter(name='zip')
def _zip(a, b):
    return zip(a, b)


@register.filter()
def zip_choices(counts, choices):
    return zip(counts, choices.names, choices.colors, choices.values)


@register.filter
def ordering_index(evaluation):
    if evaluation.state in ['new', 'prepared', 'editor_approved', 'approved']:
        return evaluation.days_until_evaluation
    elif evaluation.state == "in_evaluation":
        return 100000 + evaluation.days_left_for_evaluation
    return 200000 + evaluation.days_left_for_evaluation


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
def to_colors(choices):
    if not choices:
        # When displaying the course distribution, there are no associated voting choices.
        # In that case, we just use the colors of a unipolar scale.
        return BASE_UNIPOLAR_CHOICES['colors']
    return choices.colors


@register.filter
def statename(state):
    return STATE_NAMES.get(state)


@register.filter
def statedescription(state):
    return STATE_DESCRIPTIONS.get(state)


@register.filter
def approval_state_values(state):
    if state in APPROVAL_STATES:
        return APPROVAL_STATES[state]
    elif state in ['in_evaluation', 'evaluated', 'reviewed', 'published']:
        return APPROVAL_STATES['approved']
    return None


@register.filter
def approval_state_icon(state):
    if state in APPROVAL_STATES:
        return APPROVAL_STATES[state].icon
    elif state in ['in_evaluation', 'evaluated', 'reviewed', 'published']:
        return APPROVAL_STATES['approved'].icon
    return None


@register.filter
def can_results_page_be_seen_by(evaluation, user):
    return evaluation.can_results_page_be_seen_by(user)


@register.filter(name='can_reward_points_be_used_by')
def _can_reward_points_be_used_by(user):
    return can_reward_points_be_used_by(user)


@register.filter
def is_choice_field(field):
    return isinstance(field.field, TypedChoiceField)


@register.filter
def is_heading_field(field):
    return isinstance(field.field, HeadingField)


@register.filter
def is_user_editor_or_delegate(evaluation, user):
    return evaluation.is_user_editor_or_delegate(user)


@register.filter
def is_user_responsible_or_contributor_or_delegate(evaluation, user):
    return evaluation.is_user_responsible_or_contributor_or_delegate(user)

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
def has_nonresponsible_editor(evaluation):
    return evaluation.contributions.filter(can_edit=True).exclude(contributor__in=evaluation.course.responsibles.all()).exists()
