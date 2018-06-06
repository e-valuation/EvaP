from collections import OrderedDict

from django.contrib import messages
from django.core.exceptions import PermissionDenied, SuspiciousOperation
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils.translation import ugettext as _

from evap.evaluation.auth import participant_required
from evap.evaluation.models import Course, Semester

from evap.student.forms import QuestionnaireVotingForm
from evap.student.tools import question_id

from evap.results.tools import calculate_average_distribution, distribution_to_grade

SUCCESS_MAGIC_STRING = 'vote submitted successfully'


@participant_required
def index(request):
    # retrieve all courses, where the user is a participant and that are not new
    courses = list(set(Course.objects.filter(participants=request.user).exclude(state="new")))
    for course in courses:
        course.distribution = calculate_average_distribution(course) if course.can_user_see_grades(request.user) else None
        course.avg_grade = distribution_to_grade(course.distribution)

    voted_courses = list(set(Course.objects.filter(voters=request.user)))
    due_courses = list(set(Course.objects.filter(participants=request.user, state='in_evaluation').exclude(voters=request.user)))

    # due courses come first, then everything else in chronological order
    # some states are handled as a group because they appear the same to students
    sorter = lambda course: (
        course not in due_courses,
        course.state not in ['prepared', 'editor_approved', 'approved'],
        course.state != 'in_evaluation',
        course.state not in ['evaluated', 'reviewed'],
        course.name
    )
    courses.sort(key=sorter)

    semesters = Semester.objects.all()
    semester_list = [dict(semester_name=semester.name, id=semester.id, is_active_semester=semester.is_active_semester,
        courses=[course for course in courses if course.semester_id == semester.id]) for semester in semesters]

    template_data = dict(
        semester_list=semester_list,
        voted_courses=voted_courses,
        can_download_grades=request.user.can_download_grades,
    )
    return render(request, "student_index.html", template_data)


def get_valid_form_groups_or_render_vote_page(request, course, preview, for_rendering_in_modal=False):
    contributions_to_vote_on = course.contributions.all()
    # prevent a user from voting on themselves
    if not preview:
        contributions_to_vote_on = contributions_to_vote_on.exclude(contributor=request.user)

    form_groups = OrderedDict()
    for contribution in contributions_to_vote_on:
        questionnaires = contribution.questionnaires.all()
        if not questionnaires.exists():
            continue
        form_groups[contribution] = [QuestionnaireVotingForm(request.POST or None, contribution=contribution, questionnaire=questionnaire) for questionnaire in questionnaires]

    if all(all(form.is_valid() for form in form_group) for form_group in form_groups.values()):
        assert not preview
        return form_groups, None

    course_form_group = form_groups.pop(course.general_contribution)

    contributor_form_groups = [(contribution.contributor, contribution.label, form_group, any(form.errors for form in form_group)) for contribution, form_group in form_groups.items()]
    course_form_group_top = [questions_form for questions_form in course_form_group if questions_form.questionnaire.is_above_contributors]
    course_form_group_bottom = [questions_form for questions_form in course_form_group if questions_form.questionnaire.is_below_contributors]
    if not contributor_form_groups:
        course_form_group_top += course_form_group_bottom
        course_form_group_bottom = []

    template_data = dict(
        errors_exist=any(any(form.errors for form in form_group) for form_group in form_groups.values()),
        course_form_group_top=course_form_group_top,
        course_form_group_bottom=course_form_group_bottom,
        contributor_form_groups=contributor_form_groups,
        course=course,
        participants_warning=course.num_participants <= 5,
        preview=preview,
        vote_end_datetime=course.vote_end_datetime,
        hours_left_for_evaluation=course.time_left_for_evaluation.seconds//3600,
        minutes_left_for_evaluation=(course.time_left_for_evaluation.seconds//60)%60,
        success_magic_string=SUCCESS_MAGIC_STRING,
        success_redirect_url=reverse('student:index'),
        evaluation_ends_soon=course.evaluation_ends_soon(),
        for_rendering_in_modal=for_rendering_in_modal)
    return None, render(request, "student_vote.html", template_data)


@participant_required
def vote(request, course_id):

    course = get_object_or_404(Course, id=course_id)
    if not course.can_user_vote(request.user):
        raise PermissionDenied

    form_groups, rendered_page = get_valid_form_groups_or_render_vote_page(request, course, preview=False)
    if rendered_page is not None:
        return rendered_page

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
                    identifier = question_id(contribution, questionnaire, question)
                    value = questionnaire_form.cleaned_data.get(identifier)

                    if question.is_text_question:
                        if value:
                            question.answer_class.objects.create(
                                contribution=contribution,
                                question=question,
                                answer=value)
                    elif question.is_heading_question:
                        pass  # ignore these
                    else:
                        if value != 6:
                            answer_counter, __ = question.answer_class.objects.get_or_create(contribution=contribution, question=question, answer=value)
                            answer_counter.add_vote()
                            answer_counter.save()

        course.course_evaluated.send(sender=Course, request=request, semester=course.semester)

    messages.success(request, _("Your vote was recorded."))
    return HttpResponse(SUCCESS_MAGIC_STRING)
