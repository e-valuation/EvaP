from django.conf import settings
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import ugettext as _

from evap.evaluation.auth import participant_required
from evap.evaluation.models import Course, Semester
from evap.evaluation.tools import STUDENT_STATES_ORDERED, create_voting_form_groups, create_contributor_questionnaires

from evap.student.forms import QuestionsForm
from evap.student.tools import make_form_identifier

from collections import OrderedDict

@participant_required
def index(request):
    # retrieve all courses, where the user is a participant and that are not new
    courses = list(set(Course.objects.filter(participants=request.user).exclude(state="new")))
    voted_courses = list(set(Course.objects.filter(voters=request.user)))
    due_courses = list(set(Course.objects.filter(participants=request.user, state='inEvaluation').exclude(voters=request.user)))

    sorter = lambda course: (STUDENT_STATES_ORDERED.keys().index(course.student_state), course.vote_end_date, course.name)
    courses.sort(key=sorter)

    semesters = Semester.objects.all()
    semester_list = [dict(semester_name=semester.name, id=semester.id, courses=[course for course in courses if course.semester_id == semester.id]) for semester in semesters]

    return render(request, "student_index.html", dict(semester_list=semester_list, voted_courses=voted_courses, due_courses=due_courses))


@participant_required
def vote(request, course_id):
    # retrieve course and make sure that the user is allowed to vote
    course = get_object_or_404(Course, id=course_id)
    if not course.can_user_vote(request.user):
        raise PermissionDenied

    form_groups = create_voting_form_groups(request, course.contributions.all())

    if not all(all(form.is_valid() for form in form_group.values()) for form_group in form_groups.values()):
        
        course_questionnaires = list(form_groups[course.general_contribution].values())

        contributor_questionnaires, errors = create_contributor_questionnaires(list(form_groups.items()))

        template_data = dict(
                is_bound=course_questionnaires[0].is_bound, # is_bound states whether the form already contains user data
                course_questionnaires=course_questionnaires,
                contributor_questionnaires=contributor_questionnaires,
                errors=errors,
                course=course)
        return render(request, "student_vote.html", template_data)

    # all forms are valid
    # begin vote operation
    with transaction.atomic():
        for contribution, form_group in form_groups.items():
            for questionnaire, form in form_group.items():
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

        course.was_evaluated(request)

    messages.success(request, _("Your vote was recorded."))
    return redirect('evap.student.views.index')
