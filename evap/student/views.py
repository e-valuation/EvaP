from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render_to_response
from django.template import RequestContext
from django.utils.datastructures import SortedDict
from django.utils.translation import ugettext as _

from evap.evaluation.auth import login_required
from evap.evaluation.models import Course, Semester
from evap.evaluation.tools import questionnaires_and_contributions
from evap.student.forms import QuestionsForm
from evap.student.tools import make_form_identifier

from datetime import datetime


@login_required
def index(request):
    # retrieve all courses, which the user can evaluate at some point
    users_courses = Course.objects.filter(
            participants=request.user
        ).exclude(
            voters=request.user
        )
    # split up into current and future courses
    current_courses = users_courses.filter(state='inEvaluation')
    future_courses = users_courses.filter(state='approved')
    
    return render_to_response(
        "student_index.html",
        dict(current_courses=current_courses,
             future_courses=future_courses),
        context_instance=RequestContext(request))


@login_required
def vote(request, course_id):
    # retrieve course and make sure that the user is allowed to vote
    course = get_object_or_404(Course, id=course_id)
    if not course.can_user_vote(request.user):
        raise PermissionDenied
    
    # build forms
    forms = SortedDict()
    for questionnaire, contribution in questionnaires_and_contributions(course):
        form = QuestionsForm(request.POST or None, contribution=contribution, questionnaire=questionnaire)
        forms[(contribution, questionnaire)] = form
    
    if all(form.is_valid() for form in forms.values()):
        # begin vote operation
        with transaction.commit_on_success():
            for (contribution, questionnaire), form in forms.items():
                for question in questionnaire.question_set.all():
                    identifier = make_form_identifier(contribution, questionnaire, question)
                    value = form.cleaned_data.get(identifier)
                    
                    if type(value) in [str, unicode]:
                        value = value.strip()

                    if value == 6: #no answer
                        value = None
                    
                    # store the answer if one was given
                    if value:
                        question.answer_class.objects.create(
                            contribution=contribution,
                            question=question,
                            answer=value)
            
            # remember that the user voted already
            course.voters.add(request.user)
        
        messages.add_message(request, messages.INFO, _("Your vote was recorded."))
        return redirect('evap.student.views.index')
    else:
        return render_to_response(
            "student_vote.html",
            dict(forms=forms.values(),
                 course=course),
            context_instance=RequestContext(request))
