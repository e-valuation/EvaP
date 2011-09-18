from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render_to_response
from django.template import RequestContext
from django.utils.datastructures import SortedDict
from django.utils.translation import ugettext as _

from evaluation.auth import login_required
from evaluation.models import Course, GradeAnswer, TextAnswer
from evaluation.tools import questionnaires_and_lecturers
from student.forms import QuestionsForm
from student.tools import make_form_identifier

from datetime import datetime

@login_required
def index(request):
    users_courses = Course.objects.filter(
            vote_end_date__gte=datetime.now(),
            participants=request.user
        ).exclude(
            voters=request.user
        )
    current_courses = [course for course
                       in users_courses.filter(vote_start_date__lte=datetime.now())
                       if course.has_enough_questionnaires()]
    future_courses = [course for course
                       in users_courses.exclude(vote_start_date__lte=datetime.now())
                       if course.has_enough_questionnaires()]
    
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
    for questionnaire, lecturer in questionnaires_and_lecturers(course):
        form = QuestionsForm(request.POST or None,
                             questionnaire=questionnaire,
                             lecturer=lecturer)
        forms[(questionnaire, lecturer)] = form
    
    if all(form.is_valid() for form in forms.values()):
        # begin vote operation
        with transaction.commit_on_success():
            for k, form in forms.items():
                questionnaire, lecturer = k
                for question in questionnaire.question_set.all():
                    identifier = make_form_identifier(questionnaire,
                                                      question,
                                                      lecturer)
                    value = form.cleaned_data.get(identifier)
                    # store the answer if one was given
                    answer_args = dict(
                        course=course,
                        question=question,
                        lecturer=lecturer,
                    )
                    if question.is_grade_question() and value:
                        answer = GradeAnswer(answer=value, **answer_args)
                        answer.save()
                    elif question.is_text_question() and value and value[0]:
                        answer = TextAnswer(answer=value[0],
                                            publication_desired=value[1],
                                            **answer_args)
                        answer.save()
            
            # remember that the user voted already
            course.voters.add(request.user)
        
        messages.add_message(request, messages.INFO, _("Your vote was recorded."))
        return redirect('student.views.index')
    else:
        return render_to_response(
            "student_vote.html",
            dict(forms=forms.values(),
                 course=course),
            context_instance=RequestContext(request))
