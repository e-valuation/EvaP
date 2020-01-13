import datetime
import operator
from collections import defaultdict
from django.conf import settings
from django.contrib.auth import user_logged_in
from django.dispatch import receiver
from django.utils import translation
from django.utils.translation import LANGUAGE_SESSION_KEY, get_language


# random object that will be used to check whether a default argument value was overwritten or not
USE_DEFAULT = object()


def is_external_email(email):
    return not any([email.endswith("@" + domain) for domain in settings.INSTITUTION_EMAIL_DOMAINS])


def send_publish_notifications(evaluations, template_contributor=USE_DEFAULT, template_participant=USE_DEFAULT):
    from evap.evaluation.models import EmailTemplate

    if template_contributor == USE_DEFAULT:
        template_contributor = EmailTemplate.objects.get(name=EmailTemplate.PUBLISHING_NOTICE_CONTRIBUTOR)

    if template_participant == USE_DEFAULT:
        template_participant = EmailTemplate.objects.get(name=EmailTemplate.PUBLISHING_NOTICE_PARTICIPANT)

    evaluations_for_contributors = defaultdict(set)
    evaluations_for_participants = defaultdict(set)

    for evaluation in evaluations:
        # for evaluations with published averaged grade, all contributors and participants get a notification
        # we don't send a notification if the significance threshold isn't met
        if evaluation.can_publish_average_grade:
            if template_contributor:
                for contribution in evaluation.contributions.all():
                    if contribution.contributor:
                        evaluations_for_contributors[contribution.contributor].add(evaluation)

            if template_participant:
                for participant in evaluation.participants.all():
                    evaluations_for_participants[participant].add(evaluation)

        # if the average grade was not published, notifications are only sent for contributors who can see text answers
        elif evaluation.textanswer_set and template_contributor:
            for textanswer in evaluation.textanswer_set:
                if textanswer.contribution.contributor:
                    evaluations_for_contributors[textanswer.contribution.contributor].add(evaluation)

            for contributor in evaluation.course.responsibles.all():
                evaluations_for_contributors[contributor].add(evaluation)

    assert not evaluations_for_contributors or template_contributor
    assert not evaluations_for_participants or template_participant

    for contributor, evaluation_set in evaluations_for_contributors.items():
        body_params = {'user': contributor, 'evaluations': list(evaluation_set)}
        EmailTemplate.send_to_user(contributor, template_contributor, {}, body_params, use_cc=True)

    for participant, evaluation_set in evaluations_for_participants.items():
        body_params = {'user': participant, 'evaluations': list(evaluation_set)}
        EmailTemplate.send_to_user(participant, template_participant, {}, body_params, use_cc=True)


def sort_formset(request, formset):
    if request.POST:  # if not, there will be no cleaned_data and the models should already be sorted anyways
        formset.is_valid()  # make sure all forms have cleaned_data
        formset.forms.sort(key=lambda f: f.cleaned_data.get("order", 9001))


def date_to_datetime(date):
    return datetime.datetime(year=date.year, month=date.month, day=date.day)


@receiver(user_logged_in)
def set_or_get_language(user, request, **_kwargs):
    if user.language:
        translation.activate(user.language)
    else:
        user.language = get_language()
        user.save()
    request.session[LANGUAGE_SESSION_KEY] = user.language


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


def clean_email(email):
    if email:
        email = email.strip().lower()
        # Replace email domains in case there are multiple alias domains used in the organisation and all emails should
        # have the same domain on EvaP.
        for original_domain, replaced_domain in settings.INSTITUTION_EMAIL_REPLACEMENTS:
            if email.endswith(original_domain):
                return email[:-len(original_domain)] + replaced_domain
    return email
