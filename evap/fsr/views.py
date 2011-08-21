from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import transaction
from django.forms.models import inlineformset_factory, modelformset_factory
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render_to_response
from django.template import RequestContext
from django.utils.translation import ugettext as _

import xlrd

from evaluation.models import Semester, Course, Question, QuestionGroup
from fsr.forms import *
from fsr.tools import find_or_create_course, find_or_create_user

@login_required
def semester_index(request):
    semesters = Semester.objects.all()
    return render_to_response("fsr_semester_index.html", dict(semesters=semesters), context_instance=RequestContext(request))

@login_required
def semester_view(request, semester_id):
    semester = get_object_or_404(Semester, id=semester_id)
    courses = semester.course_set.all()
    return render_to_response("fsr_semester_view.html", dict(semester=semester, courses=courses), context_instance=RequestContext(request))

@login_required
def semester_create(request):
    form = SemesterForm(request.POST or None)
    
    if form.is_valid():
        s = form.save()
        
        messages.add_message(request, messages.INFO, _("Successfully created semester."))
        return redirect('fsr.views.semester_view', s.id)
    else:
        return render_to_response("fsr_semester_form.html", dict(form=form), context_instance=RequestContext(request))

@login_required
def semester_edit(request, semester_id):
    semester = get_object_or_404(Semester, id=semester_id)
    form = SemesterForm(request.POST or None, instance = semester)
    
    if form.is_valid():
        form.save()
        
        messages.add_message(request, messages.INFO, _("Successfully updated semester."))
        return redirect('fsr.views.semester_view', semester_id)
    else:
        return render_to_response("fsr_semester_form.html", dict(semester=semester, form=form), context_instance=RequestContext(request))

@login_required
def semester_import(request, semester_id):   
    semester = get_object_or_404(Semester, id=semester_id)
    form = ImportForm(request.POST or None, request.FILES or None)
    
    if form.is_valid():
        # extract data from form
        book = xlrd.open_workbook(file_contents=form.cleaned_data['excel_file'].read())
        vote_start_date = form.cleaned_data['vote_start_date']
        vote_end_date = form.cleaned_data['vote_end_date']
        publish_date = form.cleaned_data['publish_date']
        
        # parse table
        
        with transaction.commit_on_success():
            count = 0
            for sheet in book.sheets():
                try:
                    for row in range(1, sheet.nrows):
                        # load complete row
                        data = [sheet.cell(row,col).value for col in range(sheet.ncols)]
                        
                        # find or create student
                        student = find_or_create_user(username=data[3], first_name=data[1], last_name=data[2])
                        
                        # find or create primary lecturer
                        lecturer = find_or_create_user(username=data[9], first_name=data[7], last_name=data[8])
                        
                        # find or create course
                        course = find_or_create_course(semester, name_de=data[5], name_en=data[6], vote_start_date=vote_start_date, vote_end_date=vote_end_date, publish_date=publish_date)
                        
                        course.participants.add(student)
                        course.primary_lecturers.add(lecturer)
                        count = count + 1
                    messages.add_message(request, messages.INFO, _("Successfully imported sheet '%s'.") % sheet.name)
                except Exception,e:
                    messages.add_message(request, messages.ERROR, _("Error while importing sheet '%(name)s'. All changes undone. The error message has been: '%(error)s'") % dict(name=sheet.name, error=e))
                    raise
            messages.add_message(request, messages.INFO, _("Successfully imported %d courses.") % count)
        
        return redirect('fsr.views.semester_view', semester_id)
    else:
        return render_to_response("fsr_import.html", dict(semester=semester, form=form), context_instance=RequestContext(request))

@login_required
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
                course.primary_lectuerer_questions = form.cleaned_data['primary_lecturers']
            
            # check secondary lecturer
            if form.cleaned_data['secondary_lecturers']:
                course.secondary_lecturer_questions = form.cleaned_data['secondary_lecturers']
            
            course.save()
        
        messages.add_message(request, messages.INFO, _("Successfully assigned question groups."))
        return redirect('fsr.views.semester_view', semester_id)
    else:
        return render_to_response("fsr_semester_assign_questiongroups.html", dict(semester=semester, form=form), context_instance=RequestContext(request))

@login_required
def course_create(request, semester_id):
    semester = get_object_or_404(Semester, id=semester_id)
    form = CourseForm(request.POST or None)
    
    if form.is_valid():
        course = form.save(commit=False)
        course.semester = semester
        course.save()
        
        messages.add_message(request, messages.INFO, _("Successfully created course."))
        return redirect('fsr.views.semester_view', semester_id)
    else:
        return render_to_response("fsr_course_form.html", dict(semester=semester, form=form), context_instance=RequestContext(request))

@login_required
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
        
@login_required
def course_censor(request, semester_id, course_id):
    semester = get_object_or_404(Semester, id=semester_id)
    course = get_object_or_404(Course, id=course_id)
    censorFS = modelformset_factory(TextAnswer, form=CensorTextAnswerForm, can_order=False, can_delete=False, extra=0)
    
    formset = censorFS(request.POST or None, queryset=course.textanswer_set)
    
    if formset.is_valid():
        formset.save()
        
        messages.add_message(request, messages.INFO, _("Successfully censored course answers."))
        return redirect('fsr.views.semester_view', semester_id)
    else:
        if request.method == "POST":
            print formset.errors
        return render_to_response("fsr_course_censor.html", dict(semester=semester, formset=formset), context_instance=RequestContext(request))

@login_required
def questiongroup_index(request):
    questiongroups = QuestionGroup.objects.all()
    return render_to_response("fsr_questiongroup_index.html", dict(questiongroups=questiongroups), context_instance=RequestContext(request))

@login_required
def questiongroup_view(request, questiongroup_id):
    questiongroup = get_object_or_404(QuestionGroup, id=questiongroup_id)
    form = QuestionGroupPreviewForm(None, questiongroup=questiongroup)
    return render_to_response("fsr_questiongroup_view.html", dict(form=form, questiongroup=questiongroup), context_instance=RequestContext(request))

@login_required
def questiongroup_create(request):
    QuestionFormset = inlineformset_factory(QuestionGroup, Question, form=QuestionForm, extra=1, exclude=('question_group'))

    form = QuestionGroupForm(request.POST or None)
    formset = QuestionFormset(request.POST or None)
    
    if form.is_valid() and formset.is_valid():
        questiongroup = form.save()
        formset = QuestionFormset(request.POST or None, instance=questiongroup)
        formset.save()
        
        messages.add_message(request, messages.INFO, _("Successfully created question group."))
        return redirect('fsr.views.questiongroup_view', questiongroup.id)
    else:
        return render_to_response("fsr_questiongroup_form.html", dict(form=form, formset=formset), context_instance=RequestContext(request))

@login_required
def questiongroup_edit(request, questiongroup_id):
    questiongroup = get_object_or_404(QuestionGroup, id=questiongroup_id)
    QuestionFormset = inlineformset_factory(QuestionGroup, Question, form=QuestionForm, extra=1, exclude=('question_group'))
    
    form = QuestionGroupForm(request.POST or None, instance=questiongroup)
    formset = QuestionFormset(request.POST or None, instance=questiongroup)
    
    if form.is_valid() and formset.is_valid():
        form.save()
        formset.save()
        
        messages.add_message(request, messages.INFO, _("Successfully updated question group."))
        return redirect('fsr.views.questiongroup_view', questiongroup_id)
    else:
        return render_to_response("fsr_questiongroup_form.html", dict(questiongroup=questiongroup, form=form, formset=formset), context_instance=RequestContext(request))

@login_required
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

@login_required
def questiongroup_delete(request, questiongroup_id):
    questiongroup = get_object_or_404(QuestionGroup, id=questiongroup_id)
    
    if request.method == 'POST':
        questiongroup.delete()
        return redirect('fsr.views.questiongroup_index')
    else:
        return render_to_response("fsr_questiongroup_delete.html", dict(questiongroup=questiongroup), context_instance=RequestContext(request))
    