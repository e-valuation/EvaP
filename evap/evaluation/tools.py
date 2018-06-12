from collections import OrderedDict, defaultdict
import datetime
import operator

from django.conf import settings
from django.contrib.auth import user_logged_in
from django.dispatch import receiver
from django.utils.translation import ugettext_lazy as _
from django.utils import translation
from django.utils.translation import LANGUAGE_SESSION_KEY, get_language

LIKERT_NAMES = {
    # Translators: This includes a non breaking space in German ("Stimme voll~zu")
    1: _("Strongly agree"),
    2: _("Agree"),
    3: _("Neutral"),
    # Translators: This includes a non breaking space in German ("Stimme nicht~zu")
    4: _("Disagree"),
    5: _("Strongly disagree"),
    6: _("no answer"),
}

GRADE_NAMES = {
    1: _("1"),
    2: _("2"),
    3: _("3"),
    4: _("4"),
    5: _("5"),
    6: _("no answer"),
}

POSITIVE_YES_NO_NAMES = {
    1: _("Yes"),
    5: _("No"),
    6: _("no answer"),
}

NEGATIVE_YES_NO_NAMES = {
    1: _("No"),
    5: _("Yes"),
    6: _("no answer"),
}

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
    ('new', _('The course was newly created and will be prepared by the evaluation team.')),
    ('prepared', _('The course was prepared by the evaluation team and is now available for editing to the responsible person.')),
    ('editor_approved', _('The course was approved by a lecturer and will now be checked by the evaluation team.')),
    ('approved', _('All preparations are finished. The evaluation will begin once the defined start date is reached.')),
    ('in_evaluation', _('The course is currently in evaluation until the defined end date is reached.')),
    ('evaluated', _('The course was fully evaluated and will now be reviewed by the evaluation team.')),
    ('reviewed', _('The course was fully evaluated and reviewed by the evaluation team. You will receive an email when its results are published.')),
    ('published', _('The results for this course have been published.'))
))


def is_external_email(email):
    return not any([email.endswith("@" + domain) for domain in settings.INSTITUTION_EMAIL_DOMAINS])


def send_publish_notifications(courses, template=None):
    from evap.evaluation.models import EmailTemplate
    publish_notifications = defaultdict(set)

    if not template:
        template = EmailTemplate.objects.get(name=EmailTemplate.PUBLISHING_NOTICE)

    for course in courses:
        # for courses with published averaged grade, all contributors and participants get a notification
        # we don't send a notification if the significance threshold isn't met
        if course.can_publish_average_grade:
            for participant in course.participants.all():
                publish_notifications[participant].add(course)
            for contribution in course.contributions.all():
                if contribution.contributor:
                    publish_notifications[contribution.contributor].add(course)
        # if the average grade was not published, notifications are only sent for contributors who can see text answers
        elif course.textanswer_set:
            for textanswer in course.textanswer_set:
                if textanswer.contribution.contributor:
                    publish_notifications[textanswer.contribution.contributor].add(course)

            for contributor in course.responsible_contributors:
                publish_notifications[contributor].add(course)

    for user, course_set in publish_notifications.items():
        body_params = {'user': user, 'courses': list(course_set)}
        EmailTemplate.send_to_user(user, template, {}, body_params, use_cc=True)


def sort_formset(request, formset):
    if request.POST:  # if not, there will be no cleaned_data and the models should already be sorted anyways
        formset.is_valid()  # make sure all forms have cleaned_data
        formset.forms.sort(key=lambda f: f.cleaned_data.get("order", 9001))


def course_types_in_semester(semester):
    from evap.evaluation.models import Course
    return Course.objects.filter(semester=semester).values_list('type', flat=True).order_by().distinct()


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


def get_due_courses_for_user(user):
    from evap.evaluation.models import Course
    due_courses = dict()
    for course in Course.objects.filter(participants=user, state='in_evaluation').exclude(voters=user):
        due_courses[course] = (course.vote_end_date - datetime.date.today()).days

    # Sort courses by number of days left for evaluation and bring them to following format:
    # [(course, due_in_days), ...]
    return sorted(due_courses.items(), key=operator.itemgetter(1))
