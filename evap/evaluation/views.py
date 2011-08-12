from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import transaction
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render_to_response
from django.template import RequestContext

from evaluation.forms import QuestionsForms
from evaluation.models import Course, GradeAnswer, TextAnswer

@login_required
def student_index(request):
    courses = Course.for_user(request.user)
    return render_to_response("evaluation/student_index.html", dict(courses=courses))


@login_required
def student_vote(request, course_id):
    # retrieve course and make sure that the user is allowed to vote
    course = get_object_or_404(Course, id=course_id)
    if not course.can_user_vote(request.user):
        return HttpResponseForbidden()
    
    # retrieve questionnaires and build form
    questionnaires = course.questionnaire_set.all()
    form = QuestionsForms(request.POST or None, questionnaires=questionnaires)
    
    if form.is_valid():
        with transaction.commit_on_success():
            # iterate over all questions in all questionnaires
            for questionnaire in questionnaires:
                for question in questionnaire.questions():
                    # stores the answer if one was given
                    value = form.cleaned_data.get("question_%d_%d" % (questionnaire.id, question.id))
                    if value:
                        answer = question.answer_class()(questionnaire=questionnaire, question=question, answer=value)
                        answer.save()
            # remember that the user voted already
            course.voters.add(request.user)
        
        messages.add_message(request, messages.INFO, _("Your vote was recorded."))
        return redirect("/student")
    else:
        return render_to_response(
            "evaluation/student_vote.html",
            dict(form=form),
            context_instance=RequestContext(request))
