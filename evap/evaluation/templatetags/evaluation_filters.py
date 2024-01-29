from collections import namedtuple

from django.forms import TypedChoiceField
from django.template import Library
from django.utils.translation import gettext_lazy as _

from evap.evaluation.models import BASE_UNIPOLAR_CHOICES, Contribution, Evaluation
from evap.results.tools import RatingResult
from evap.rewards.tools import can_reward_points_be_used_by
from evap.student.forms import HeadingField

# the names displayed for contributors
STATE_NAMES = {
    Evaluation.State.NEW: _("new"),
    Evaluation.State.PREPARED: _("prepared"),
    Evaluation.State.EDITOR_APPROVED: _("editor approved"),
    Evaluation.State.APPROVED: _("approved"),
    Evaluation.State.IN_EVALUATION: _("in evaluation"),
    Evaluation.State.EVALUATED: _("evaluated"),
    Evaluation.State.REVIEWED: _("reviewed"),
    Evaluation.State.PUBLISHED: _("published"),
}

STR_TO_STATE = {s: i for i, s in Evaluation.STATE_STR_CONVERSION.items()}


# the descriptions used in tooltips for contributors
STATE_DESCRIPTIONS = {
    Evaluation.State.NEW: _("The evaluation was newly created and will be prepared by the evaluation team."),
    Evaluation.State.PREPARED: _(
        "The evaluation was prepared by the evaluation team and is now available for editors."
    ),
    Evaluation.State.EDITOR_APPROVED: _(
        "The evaluation was approved by an editor and will now be checked by the evaluation team."
    ),
    Evaluation.State.APPROVED: _(
        "All preparations are finished. The evaluation will begin once the defined start date is reached."
    ),
    Evaluation.State.IN_EVALUATION: _("The evaluation is currently running until the defined end date is reached."),
    Evaluation.State.EVALUATED: _("The evaluation has finished and will now be reviewed by the evaluation team."),
    Evaluation.State.REVIEWED: _(
        "The evaluation has finished and was reviewed by the evaluation team. You will receive an email when its results are published."
    ),
    Evaluation.State.PUBLISHED: _("The results for this evaluation have been published."),
}


# values for approval states shown to staff
StateValues = namedtuple("StateValues", ("order", "icon", "filter", "description"))
APPROVAL_STATES = {
    Evaluation.State.NEW: StateValues(
        0,
        "fas fa-circle icon-yellow",
        Evaluation.State.NEW,
        _("In preparation"),
    ),
    Evaluation.State.PREPARED: StateValues(
        2,
        "far fa-square icon-gray",
        Evaluation.State.PREPARED,
        _("Awaiting editor review"),
    ),
    Evaluation.State.EDITOR_APPROVED: StateValues(
        1,
        "far fa-square-check icon-yellow",
        Evaluation.State.EDITOR_APPROVED,
        _("Approved by editor, awaiting manager review"),
    ),
    Evaluation.State.APPROVED: StateValues(
        3, "far fa-square-check icon-green", Evaluation.State.APPROVED, _("Approved by manager")
    ),
}


register = Library()


@register.filter(name="zip")
def _zip(a, b):
    return zip(a, b, strict=True)


@register.filter
def ordering_index(evaluation):
    if evaluation.state < Evaluation.State.IN_EVALUATION:
        return evaluation.days_until_evaluation
    if evaluation.state == Evaluation.State.IN_EVALUATION:
        return 100000 + evaluation.days_left_for_evaluation
    return 200000 + evaluation.days_left_for_evaluation


# from http://www.jongales.com/blog/2009/10/19/percentage-django-template-tag/
@register.filter
def percentage(fraction, population):
    try:
        return f"{int(float(fraction) / float(population) * 100):.0f}%"
    except ValueError:
        return None
    except ZeroDivisionError:
        return None


@register.filter
def percentage_one_decimal(fraction, population):
    try:
        return f"{float(fraction) / float(population) * 100:.1f}%"
    except ValueError:
        return None
    except ZeroDivisionError:
        return None


@register.filter
def to_colors(question_result: RatingResult | None):
    if question_result is None:
        # When displaying the course distribution, there are no associated voting choices.
        # In that case, we just use the colors of a unipolar scale.
        return BASE_UNIPOLAR_CHOICES["colors"][:-1]
    return question_result.colors


@register.filter
def weight_info(evaluation):
    try:
        course = evaluation.course
    except AttributeError:
        return None
    if course.evaluation_weight_sum and course.evaluation_count > 1:
        return percentage(evaluation.weight, course.evaluation_weight_sum)
    return None


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
    return APPROVAL_STATES[Evaluation.State.APPROVED]


@register.filter
def approval_state_icon(state):
    return approval_state_values(state).icon


@register.filter
def can_results_page_be_seen_by(evaluation, user):
    return evaluation.can_results_page_be_seen_by(user)


@register.filter(name="can_reward_points_be_used_by")
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
        "debug": "info",
        "info": "info",
        "success": "success",
        "warning": "warning",
        "error": "danger",
    }.get(level, "info")


@register.filter
def hours_and_minutes(time_left_for_evaluation):
    hours = time_left_for_evaluation.seconds // 3600
    minutes = (time_left_for_evaluation.seconds // 60) % 60
    return f"{hours:02}:{minutes:02}"


@register.filter
def has_nonresponsible_editor(evaluation):
    return (
        evaluation.contributions.filter(role=Contribution.Role.EDITOR)
        .exclude(contributor__in=evaluation.course.responsibles.all())
        .exists()
    )


@register.filter
def order_by(iterable, attribute):
    return sorted(iterable, key=lambda item: getattr(item, attribute))


@register.filter
def get(dictionary, key):
    return dictionary.get(key)


@register.filter
def add_class(widget, class_name_to_add: str):
    new_class = class_name_to_add + " " + widget["attrs"]["class"] if "class" in widget["attrs"] else class_name_to_add
    widget["attrs"].update({"class": new_class})
    return widget
