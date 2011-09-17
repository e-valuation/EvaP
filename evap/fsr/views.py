from django.contrib import messages
from django.forms.models import inlineformset_factory, modelformset_factory
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render_to_response
from django.template import RequestContext
from django.utils.translation import ugettext as _

from evaluation.auth import fsr_required
from evaluation.models import Semester, Course, Question, QuestionGroup
from fsr.forms import *
from fsr.importers import ExcelImporter

@fsr_required
def semester_index(request):
    semesters = Semester.objects.all()
    return render_to_response("fsr_semester_index.html", dict(semesters=semesters), context_instance=RequestContext(request))

@fsr_required
def semester_view(request, semester_id):
    semester = get_object_or_404(Semester, id=semester_id)
    
    # XXX: The Django 1.3 ORM has a bug in its aggregation part. The correct to be used here would be:
    #   courses = semester.course_set.annotate(num_participants=Count('participants'), num_voters=Count('voters'))
    # But code returns wrong values (due to the fact that both `participants` and `voters` point to the
    # same table, I guess. To work around that, we use hard-coded subselects here:
    courses = semester.course_set.extra(
        select={
            'num_participants': "SELECT COUNT(*) "
                                "FROM evaluation_course_participants "
                                "WHERE evaluation_course_participants.course_id = evaluation_course.id",
            'num_voters': "SELECT COUNT(*) "
                          "FROM evaluation_course_voters "
                          "WHERE evaluation_course_voters.course_id = evaluation_course.id"
        }
    )
    
    return render_to_response("fsr_semester_view.html", dict(semester=semester, courses=courses), context_instance=RequestContext(request))

@fsr_required
def semester_create(request):
    form = SemesterForm(request.POST or None)
    
    if form.is_valid():
        s = form.save()
        
        messages.add_message(request, messages.INFO, _("Successfully created semester."))
        return redirect('fsr.views.semester_view', s.id)
    else:
        return render_to_response("fsr_semester_form.html", dict(form=form), context_instance=RequestContext(request))

@fsr_required
def semester_edit(request, semester_id):
    semester = get_object_or_404(Semester, id=semester_id)
    form = SemesterForm(request.POST or None, instance = semester)
    
    if form.is_valid():
        s = form.save()
        
        messages.add_message(request, messages.INFO, _("Successfully updated semester."))
        return redirect('fsr.views.semester_view', s.id)
    else:
        return render_to_response("fsr_semester_form.html", dict(semester=semester, form=form), context_instance=RequestContext(request))

@fsr_required
def semester_delete(request, semester_id):
    semester = get_object_or_404(Semester, id=semester_id)
    
    if request.method == 'POST':
        semester.delete()
        return redirect('fsr.views.semester_index')
    else:
        return render_to_response("fsr_semester_delete.html", dict(semester=semester), context_instance=RequestContext(request))

@fsr_required
def semester_publish(request, semester_id):
    semester = get_object_or_404(Semester, id=semester_id)
    publishFS = modelformset_factory(Course, formset=PublishCourseFormSet, fields=('visible', ), can_order=False, can_delete=False, extra=0)
    formset = publishFS(request.POST or None, queryset=semester.course_set.filter(visible=False))
    
    if formset.is_valid():
        count = len(formset.save())
        
        messages.add_message(request, messages.INFO, _("Successfully published %d courses.") % count)
        return redirect('fsr.views.semester_view', semester.id)
    else:
        return render_to_response("fsr_semester_publish.html", dict(semester=semester, formset=formset), context_instance=RequestContext(request))

@fsr_required
def semester_import(request, semester_id):   
    semester = get_object_or_404(Semester, id=semester_id)
    form = ImportForm(request.POST or None, request.FILES or None)
    
    if form.is_valid():
        # extract data from form
        excel_file = form.cleaned_data['excel_file']
        vote_start_date = form.cleaned_data['vote_start_date']
        vote_end_date = form.cleaned_data['vote_end_date']
        
        # parse table
        ExcelImporter.process(request, excel_file, semester, vote_start_date, vote_end_date)
        return redirect('fsr.views.semester_view', semester_id)
    else:
        return render_to_response("fsr_import.html", dict(semester=semester, form=form), context_instance=RequestContext(request))

@fsr_required
def semester_assign_questiongroups(request, semester_id):
    semester = get_object_or_404(Semester, id=semester_id)
    form = QuestionGroupsAssignForm(request.POST or None, semester=semester, extras=('primary_lecturers', 'secondary_lecturers'))
    
    if form.is_valid():
        for course in semester.course_set.all():
            # check course itself
            if form.cleaned_data[course.kind]:
                course.general_questions = form.cleaned_data[course.kind]
            
            # check primary lecturer
            if form.cleaned_data['primary_lecturers']:
                course.primary_lecturer_questions = form.cleaned_data['primary_lecturers']
            
            # check secondary lecturer
            if form.cleaned_data['secondary_lecturers']:
                course.secondary_lecturer_questions = form.cleaned_data['secondary_lecturers']
            
            course.save()
        
        messages.add_message(request, messages.INFO, _("Successfully assigned question groups."))
        return redirect('fsr.views.semester_view', semester_id)
    else:
        return render_to_response("fsr_semester_assign_questiongroups.html", dict(semester=semester, form=form), context_instance=RequestContext(request))

@fsr_required
def course_create(request, semester_id):
    semester = get_object_or_404(Semester, id=semester_id)
    form = CourseForm(request.POST or None, initial={'semester':semester})
    
    if form.is_valid():
        form.save()

        messages.add_message(request, messages.INFO, _("Successfully created course."))
        return redirect('fsr.views.semester_view', semester_id)
    else:
        return render_to_response("fsr_course_form.html", dict(semester=semester, form=form), context_instance=RequestContext(request))

@fsr_required
def course_edit(request, semester_id, course_id):
    semester = get_object_or_404(Semester, id=semester_id)
    course = get_object_or_404(Course, id=course_id)
    form = CourseForm(request.POST or None, instance = course)
    
    if form.is_valid():
        form.save()
        
        messages.add_message(request, messages.INFO, _("Successfully updated course."))
        return redirect('fsr.views.semester_view', semester_id)
    else:
        return render_to_response("fsr_course_form.html", dict(semester=semester, form=form), context_instance=RequestContext(request))

@fsr_required
def course_delete(request, semester_id, course_id):
    semester = get_object_or_404(Semester, id=semester_id)
    course = get_object_or_404(Course, id=course_id)
    
    if request.method == 'POST':
        course.delete()
        return redirect('fsr.views.semester_view', semester_id)
    else:
        return render_to_response("fsr_course_delete.html", dict(semester=semester), context_instance=RequestContext(request))

@fsr_required
def course_censor(request, semester_id, course_id):
    semester = get_object_or_404(Semester, id=semester_id)
    course = get_object_or_404(Course, id=course_id)
    censorFS = modelformset_factory(TextAnswer, form=CensorTextAnswerForm, can_order=False, can_delete=False, extra=0)
    
    formset = censorFS(request.POST or None, queryset=course.textanswer_set)
    
    if formset.is_valid():
        count = 0
        for form in formset:
            if form.cleaned_data['action'] == 1:
                # approved
                pass
            elif form.cleaned_data['action'] == 2:
                # censored
                form.instance.censored_answer = form.cleaned_data['censored_answer']
            elif form.cleaned_data['action'] == 3:
                # hide
                form.instance.hidden = True
            else:
                # needs further review
                continue
            
            form.instance.checked = True
            form.instance.save()
            count = count + 1
        
        messages.add_message(request, messages.INFO, _("Successfully censored %d course answers.") % count)
        return redirect('fsr.views.semester_view', semester_id)
    else:
        if request.method == "POST":
            print formset.errors
        return render_to_response("fsr_course_censor.html", dict(semester=semester, formset=formset), context_instance=RequestContext(request))
    
@fsr_required
def questiongroup_index(request):
    questiongroups = QuestionGroup.objects.order_by('obsolete')
    return render_to_response("fsr_questiongroup_index.html", dict(questiongroups=questiongroups), context_instance=RequestContext(request))

@fsr_required
def questiongroup_view(request, questiongroup_id):
    questiongroup = get_object_or_404(QuestionGroup, id=questiongroup_id)
    form = QuestionGroupPreviewForm(None, questiongroup=questiongroup)
    return render_to_response("fsr_questiongroup_view.html", dict(form=form, questiongroup=questiongroup), context_instance=RequestContext(request))

@fsr_required
def questiongroup_create(request):
    questiongroup = QuestionGroup()
    QuestionFormset = inlineformset_factory(QuestionGroup, Question, formset=QuestionFormSet, form=QuestionForm, extra=1, exclude=('question_group'))

    form = QuestionGroupForm(request.POST or None, instance=questiongroup)
    formset = QuestionFormset(request.POST or None, instance=questiongroup)
    
    if form.is_valid() and formset.is_valid():
        q = form.save()
        formset.save()
        
        messages.add_message(request, messages.INFO, _("Successfully created question group."))
        return redirect('fsr.views.questiongroup_index')
    else:
        return render_to_response("fsr_questiongroup_form.html", dict(form=form, formset=formset), context_instance=RequestContext(request))

@fsr_required
def questiongroup_edit(request, questiongroup_id):
    questiongroup = get_object_or_404(QuestionGroup, id=questiongroup_id)
    QuestionFormset = inlineformset_factory(QuestionGroup, Question, formset=QuestionFormSet, form=QuestionForm, extra=1, exclude=('question_group'))
    
    form = QuestionGroupForm(request.POST or None, instance=questiongroup)
    formset = QuestionFormset(request.POST or None, instance=questiongroup)
    
    if questiongroup.obsolete:
        messages.add_message(request, messages.INFO, _("Obsolete question groups cannot be edited."))
        return redirect('fsr.views.questiongroup_index')
    
    if form.is_valid() and formset.is_valid():
        form.save()
        formset.save()
        
        messages.add_message(request, messages.INFO, _("Successfully updated question group."))
        return redirect('fsr.views.questiongroup_index')
    else:
        return render_to_response("fsr_questiongroup_form.html", dict(questiongroup=questiongroup, form=form, formset=formset), context_instance=RequestContext(request))

@fsr_required
def questiongroup_copy(request, questiongroup_id):
    questiongroup = get_object_or_404(QuestionGroup, id=questiongroup_id)
    form = QuestionGroupForm(request.POST or None)
    
    if form.is_valid():
        qg = form.save()
        for question in questiongroup.question_set.all():
            question.pk = None
            question.question_group = qg
            question.save()
        
        messages.add_message(request, messages.INFO, _("Successfully copied question group."))
        return redirect('fsr.views.questiongroup_view', qg.id)
    else:
        return render_to_response("fsr_questiongroup_copy.html", dict(questiongroup=questiongroup, form=form), context_instance=RequestContext(request))

@fsr_required
def questiongroup_delete(request, questiongroup_id):
    questiongroup = get_object_or_404(QuestionGroup, id=questiongroup_id)
    
    if request.method == 'POST':
        questiongroup.delete()
        return redirect('fsr.views.questiongroup_index')
    else:
        return render_to_response("fsr_questiongroup_delete.html", dict(questiongroup=questiongroup), context_instance=RequestContext(request))

@fsr_required
def user_index(request):
    users = User.objects.order_by("last_name", "first_name")
    return render_to_response("fsr_user_index.html", dict(users=users), context_instance=RequestContext(request))

@fsr_required
def user_create(request):
    profile = UserProfile(user=User())
    form = UserForm(request.POST or None, instance=profile)
    
    if form.is_valid():
        #profile.user.save()
        form.save()
        
        messages.add_message(request, messages.INFO, _("Successfully created user."))
        return redirect('fsr.views.user_index')
    else:
        return render_to_response("fsr_user_form.html", dict(form=form), context_instance=RequestContext(request))

@fsr_required
def user_edit(request, user_id):
    user = get_object_or_404(User, id=user_id)
    form = UserForm(request.POST or None, request.FILES or None, instance=user.get_profile())
    
    if form.is_valid():
        form.save()
        
        messages.add_message(request, messages.INFO, _("Successfully updated user."))
        return redirect('fsr.views.user_index')
    else:
        return render_to_response("fsr_user_form.html", dict(form=form), context_instance=RequestContext(request))

@fsr_required
def user_delete(request, user_id):
    user = get_object_or_404(User, id=user_id)
    
    if request.method == 'POST':
        user.delete()
        return redirect('fsr.views.user_index')
    else:
        return render_to_response("fsr_user_delete.html", dict(user=user), context_instance=RequestContext(request))
    
@fsr_required
def user_key_new(request, user_id):
    user = get_object_or_404(User, id=user_id)
    profile = user.get_profile()
    profile.generate_logon_key()
    profile.save()
    
    return redirect('fsr.views.user_index')
    
@fsr_required
def user_key_remove(request, user_id):
    user = get_object_or_404(User, id=user_id)
    profile = user.get_profile()
    profile.logon_key = None
    profile.save()
    
    return redirect('fsr.views.user_index')