import datetime
import operator
from collections import OrderedDict, defaultdict
from django.conf import settings
from django.contrib.auth import user_logged_in
from django.dispatch import receiver
from django.utils import translation
from django.utils.translation import LANGUAGE_SESSION_KEY, get_language, ugettext_lazy as _


# the names used for contributors and staff
STATES_ORDERED = OrderedDict((
    ('new', _('new')),
    ('prepared', _('prepared')),
    ('editor_approved', _('lecturer approved')),
    ('approved', _('approved')),
    ('in_evaluation', _('in evaluation')),
    ('evaluated', _('evaluated')),
    ('reviewed', _('reviewed')),
    ('published', _('published'))
))

# the descriptions used in tooltips for contributors
STATE_DESCRIPTIONS = OrderedDict((
    ('new', _('The evaluation was newly created and will be prepared by the evaluation team.')),
    ('prepared', _('The evaluation was prepared by the evaluation team and is now available for editing to the responsible person.')),
    ('editor_approved', _('The evaluation was approved by a lecturer and will now be checked by the evaluation team.')),
    ('approved', _('All preparations are finished. The evaluation will begin once the defined start date is reached.')),
    ('in_evaluation', _('The evaluation is currently running until the defined end date is reached.')),
    ('evaluated', _('The evaluation has finished and will now be reviewed by the evaluation team.')),
    ('reviewed', _('The evaluation has finished and was reviewed by the evaluation team. You will receive an email when its results are published.')),
    ('published', _('The results for this evaluation have been published.'))
))


def is_external_email(email):
    return not any([email.endswith("@" + domain) for domain in settings.INSTITUTION_EMAIL_DOMAINS])


def send_publish_notifications(evaluations, template=None):
    from evap.evaluation.models import EmailTemplate
    publish_notifications = defaultdict(set)

    if not template:
        template = EmailTemplate.objects.get(name=EmailTemplate.PUBLISHING_NOTICE)

    for evaluation in evaluations:
        # for evaluations with published averaged grade, all contributors and participants get a notification
        # we don't send a notification if the significance threshold isn't met
        if evaluation.can_publish_average_grade:
            for participant in evaluation.participants.all():
                publish_notifications[participant].add(evaluation)
            for contribution in evaluation.contributions.all():
                if contribution.contributor:
                    publish_notifications[contribution.contributor].add(evaluation)
        # if the average grade was not published, notifications are only sent for contributors who can see text answers
        elif evaluation.textanswer_set:
            for textanswer in evaluation.textanswer_set:
                if textanswer.contribution.contributor:
                    publish_notifications[textanswer.contribution.contributor].add(evaluation)

            for contributor in evaluation.responsible_contributors:
                publish_notifications[contributor].add(evaluation)

    for user, evaluation_set in publish_notifications.items():
        body_params = {'user': user, 'evaluations': list(evaluation_set)}
        EmailTemplate.send_to_user(user, template, {}, body_params, use_cc=True)


def sort_formset(request, formset):
    if request.POST:  # if not, there will be no cleaned_data and the models should already be sorted anyways
        formset.is_valid()  # make sure all forms have cleaned_data
        formset.forms.sort(key=lambda f: f.cleaned_data.get("order", 9001))


def course_types_in_semester(semester):
    from evap.evaluation.models import Evaluation
    return Evaluation.objects.filter(course__semester=semester).values_list('type', flat=True).order_by().distinct()


def date_to_datetime(date):
    return datetime.datetime(year=date.year, month=date.month, day=date.day)


@receiver(user_logged_in)
def set_or_get_language(user, request, **_kwargs):
    if user.language:
        request.session[LANGUAGE_SESSION_KEY] = user.language
        translation.activate(user.language)
    else:
        user.language = get_language()
        user.save()


def get_due_evaluations_for_user(user):
    from evap.evaluation.models import Evaluation
    due_evaluations = dict()
    for evaluation in Evaluation.objects.filter(participants=user, state='in_evaluation').exclude(voters=user):
        due_evaluations[evaluation] = (evaluation.vote_end_date - datetime.date.today()).days

    # Sort evaluations by number of days left for evaluation and bring them to following format:
    # [(evaluation, due_in_days), ...]
    return sorted(due_evaluations.items(), key=operator.itemgetter(1))


def get_parameter_from_url_or_session(request, parameter, default=False):
    result = request.GET.get(parameter, None)
    if result is None:  # if no parameter is given take session value
        result = request.session.get(parameter, default)
    else:
        result = {'true': True, 'false': False}.get(result.lower())  # convert parameter to boolean
    request.session[parameter] = result  # store value for session
    return result


def translate(**kwargs):
    # get_language may return None if there is no session (e.g. during management commands)
    return property(lambda self: getattr(self, kwargs[get_language() or 'en']))
