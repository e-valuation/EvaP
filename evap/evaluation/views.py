from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import get_object_or_404, redirect, render_to_response
from django.template import RequestContext

from evaluation.forms import QuestionsForms
from evaluation.models import Course

@login_required
def student_index(request):
    courses = Course.for_user(request.user)
    return render_to_response("evaluation/student_index.html", dict(courses=courses))


@login_required
def student_vote(request, course_id):
    course = get_object_or_404(Course, id=course_id)
    
    # FIXME: ensure that user can vote on this lecture
    
    form = QuestionsForms(request.POST or None,
                          questions = course.questionnaire_set.get().question_group.question_set.all())
    
    if form.is_valid():
        
        # FIXME: store results
        
        return redirect("/student")
    else:
        return render_to_response(
            "evaluation/student_vote.html",
            dict(form=form),
            context_instance=RequestContext(request))
