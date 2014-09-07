from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render_to_response
from django.template import RequestContext
from django.utils.translation import ugettext as _

from evap.evaluation.auth import login_required
from evap.evaluation.models import Course, Semester, UserProfile
from evap.evaluation.tools import questionnaires_and_contributions_by_contributor, STUDENT_STATES_ORDERED

from evap.student.forms import QuestionsForm
from evap.student.tools import make_form_identifier

from collections import OrderedDict

@login_required
def index(request):
    # retrieve all courses, where the user is a participant and that are not new
    courses = list(set(Course.objects.filter(participants=request.user).exclude(state="new")))
    voted_courses = list(set(Course.objects.filter(voters=request.user)))

    sorter = lambda course: (STUDENT_STATES_ORDERED.keys().index(course.student_state), course.name)
    courses.sort(key=sorter)

    semesters = Semester.objects.all()
    semester_list = [dict(semester_name=semester.name, id=semester.id, courses=[course for course in courses if course.semester_id == semester.id]) for semester in semesters]

    return render_to_response(
        "student_index.html",
        dict(semester_list=semester_list, voted_courses=voted_courses),
        context_instance=RequestContext(request))


@login_required
def vote(request, course_id):
    # retrieve course and make sure that the user is allowed to vote
    course = get_object_or_404(Course, id=course_id)
    if not course.can_user_vote(request.user):
        raise PermissionDenied

    # build forms
    form_group = {}
    contributors_with_questionnaires = questionnaires_and_contributions_by_contributor(course)
    for contributor in contributors_with_questionnaires:
        for questionnaire, contribution in contributors_with_questionnaires[contributor]:
            form = QuestionsForm(request.POST or None, contribution=contribution, questionnaire=questionnaire)
            if form.contribution.contributor == request.user:
                continue # users shall not vote about themselves
            if contributor not in form_group:
                form_group[contributor] = OrderedDict()
            form_group[contributor][(contribution, questionnaire)] = form

    for contributor in form_group:
        for (contribution, questionnaire), form in form_group[contributor].items():
            for question in questionnaire.question_set.all():
                identifier = make_form_identifier(contribution, questionnaire, question)

    for contributor in form_group:
        for form in form_group[contributor].values():
            if form.is_valid():
                continue
            course_forms = []
            contributor_questionnaires = {}
            errors = []

            for form in form_group[None].values():
                course_forms.append(form)

            for contributor in form_group:
                if contributor is None:
                    continue
                user_profile = UserProfile.get_for_user(contributor)
                contributor_questionnaires[user_profile] = form_group[contributor].values()
                for form in form_group[contributor].values():
                    if form.errors:
                        errors.append(contributor.id)

            return render_to_response(
                "student_vote.html",
                dict(course_forms=course_forms,
                     contributor_questionnaires=contributor_questionnaires,
                     errors=errors,
                     course=course),
                context_instance=RequestContext(request))

    # all forms are valid
    # begin vote operation
    with transaction.commit_on_success():
        for contributor in form_group:
            for (contribution, questionnaire), form in form_group[contributor].items():
                for question in questionnaire.question_set.all():
                    identifier = make_form_identifier(contribution, questionnaire, question)
                    value = form.cleaned_data.get(identifier)

                    if type(value) in [str, unicode]:
                        value = value.strip()

                    if value == 6: # no answer
                        value = None

                    # store the answer if one was given
                    if value:
                        question.answer_class.objects.create(
                            contribution=contribution,
                            question=question,
                            answer=value)

        # remember that the user voted already
        course.voters.add(request.user)

    messages.info(request, _("Your vote was recorded."))
    return redirect('evap.student.views.index')
