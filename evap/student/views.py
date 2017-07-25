from collections import OrderedDict

from django.contrib import messages
from django.core.exceptions import PermissionDenied, SuspiciousOperation
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import ugettext as _

from evap.evaluation.auth import participant_required
from evap.evaluation.models import Course, Semester
from evap.evaluation.tools import STUDENT_STATES_ORDERED

from evap.student.forms import QuestionsForm
from evap.student.tools import make_form_identifier


@participant_required
def index(request):
    # retrieve all courses, where the user is a participant and that are not new
    courses = list(set(Course.objects.filter(participants=request.user).exclude(state="new")))
    voted_courses = list(set(Course.objects.filter(voters=request.user)))
    due_courses = list(set(Course.objects.filter(participants=request.user, state='in_evaluation').exclude(voters=request.user)))

    sorter = lambda course: (list(STUDENT_STATES_ORDERED.keys()).index(course.student_state), course.vote_end_date, course.name)
    courses.sort(key=sorter)

    semesters = Semester.objects.all()
    semester_list = [dict(semester_name=semester.name, id=semester.id, is_active_semester=semester.is_active_semester,
        courses=[course for course in courses if course.semester_id == semester.id]) for semester in semesters]

    template_data = dict(
        semester_list=semester_list,
        voted_courses=voted_courses,
        due_courses=due_courses,
        can_download_grades=request.user.can_download_grades,
    )
    return render(request, "student_index.html", template_data)


def vote_preview(request, course, for_rendering_in_modal=False):
    """
        Renders a preview of the voting page for the given course.
        Not used by the student app itself, but by staff and contributor.
    """
    form_groups = helper_create_voting_form_groups(request, course.contributions.all())
    course_form_group = form_groups.pop(course.general_contribution)
    contributor_form_groups = list((contribution.contributor, contribution.label, form_group, False) for contribution, form_group in form_groups.items())

    template_data = dict(
        errors_exist=False,
        course_form_group=course_form_group,
        contributor_form_groups=contributor_form_groups,
        course=course,
        preview=True,
        for_rendering_in_modal=for_rendering_in_modal)
    return render(request, "student_vote.html", template_data)


@participant_required
def vote(request, course_id):
    # retrieve course and make sure that the user is allowed to vote
    course = get_object_or_404(Course, id=course_id)
    if not course.can_user_vote(request.user):
        raise PermissionDenied

    # prevent a user from voting on themselves.
    contributions_to_vote_on = course.contributions.exclude(contributor=request.user).all()
    form_groups = helper_create_voting_form_groups(request, contributions_to_vote_on)

    if not all(all(form.is_valid() for form in form_group) for form_group in form_groups.values()):
        errors_exist = any(helper_has_errors(form_group) for form_group in form_groups.values())

        course_form_group = form_groups.pop(course.general_contribution)

        contributor_form_groups = list((contribution.contributor, contribution.label, form_group, helper_has_errors(form_group)) for contribution, form_group in form_groups.items())

        template_data = dict(
            errors_exist=errors_exist,
            course_form_group=course_form_group,
            contributor_form_groups=contributor_form_groups,
            course=course,
            participants_warning=course.num_participants <= 5,
            preview=False)
        return render(request, "student_vote.html", template_data)

    # all forms are valid, begin vote operation
    with transaction.atomic():
        # add user to course.voters
        # not using course.voters.add(request.user) since it fails silently when done twice.
        # manually inserting like this gives us the 'created' return value and ensures at the database level that nobody votes twice.
        __, created = course.voters.through.objects.get_or_create(userprofile_id=request.user.pk, course_id=course.pk)
        if not created:  # vote already got recorded, bail out
            raise SuspiciousOperation("A second vote has been received shortly after the first one.")

        for contribution, form_group in form_groups.items():
            for questionnaire_form in form_group:
                questionnaire = questionnaire_form.questionnaire
                for question in questionnaire.question_set.all():
                    identifier = make_form_identifier(contribution, questionnaire, question)
                    value = questionnaire_form.cleaned_data.get(identifier)

                    if question.is_text_question:
                        if value:
                            question.answer_class.objects.create(
                                contribution=contribution,
                                question=question,
                                answer=value)
                    else:
                        if value != 6:
                            answer_counter, __ = question.answer_class.objects.get_or_create(contribution=contribution, question=question, answer=value)
                            answer_counter.add_vote()
                            answer_counter.save()

        course.course_evaluated.send(sender=Course, request=request, semester=course.semester)

    messages.success(request, _("Your vote was recorded."))
    return redirect('student:index')


def helper_create_voting_form_groups(request, contributions):
    form_groups = OrderedDict()
    for contribution in contributions:
        questionnaires = contribution.questionnaires.all()
        if not questionnaires.exists():
            continue
        form_groups[contribution] = [QuestionsForm(request.POST or None, contribution=contribution, questionnaire=questionnaire) for questionnaire in questionnaires]
    return form_groups


def helper_has_errors(form_group):
    return any(form.errors for form in form_group)
