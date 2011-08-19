from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import transaction
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render_to_response
from django.template import RequestContext
from django.utils.translation import ugettext as _

from evaluation.models import Course, GradeAnswer, TextAnswer
from student.forms import QuestionsForms
from student.tools import make_form_identifier, questiongroups_and_lecturers

@login_required
def index(request):
    courses = Course.for_user(request.user)
    return render_to_response(
        "student_index.html",
        dict(courses=courses),
        context_instance=RequestContext(request))


@login_required
def vote(request, course_id):
    # retrieve course and make sure that the user is allowed to vote
    course = get_object_or_404(Course, id=course_id)
    if not course.can_user_vote(request.user):
        return HttpResponseForbidden()
    
    # retrieve questionnaires and build form
    form = QuestionsForms(request.POST or None, course=course)
    
    if form.is_valid():
        with transaction.commit_on_success():
            for question_group, lecturer in questiongroups_and_lecturers(course):
                for question in question_group.question_set.all():
                    identifier = make_form_identifier(question_group,
                                                      question,
                                                      lecturer)
                    value = form.cleaned_data.get(identifier)
                    # store the answer if one was given
                    if value:
                        answer = question.answer_class()(
                            course=course,
                            question=question,
                            lecturer=None,
                            answer=value)
                        answer.save()
            # remember that the user voted already
            course.voters.add(request.user)
        
        messages.add_message(request, messages.INFO, _("Your vote was recorded."))
        return redirect('student.views.index')
    else:
        return render_to_response(
            "student_vote.html",
            dict(form=form),
            context_instance=RequestContext(request))
