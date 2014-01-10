from django.contrib import messages
from django.contrib.auth.models import User
from django.core.cache import cache
from django.forms.models import inlineformset_factory, modelformset_factory
from django.shortcuts import get_object_or_404, redirect, render_to_response
from django.template import RequestContext
from django.utils.datastructures import SortedDict
from django.utils.translation import ugettext as _
from django.utils.translation import ugettext_lazy

from evap.evaluation.auth import fsr_required
from evap.evaluation.models import Contribution, Course, Question, Questionnaire, Semester, TextAnswer, UserProfile
from evap.evaluation.tools import questionnaires_and_contributions, STATES_ORDERED
from evap.fsr.forms import ContributionForm, AtLeastOneFormSet, ReviewTextAnswerForm, CourseForm, \
                           CourseEmailForm, EmailTemplateForm, IdLessQuestionFormSet, ImportForm, \
                           LotteryForm, QuestionForm, QuestionnaireForm, QuestionnairesAssignForm, \
                           SelectCourseForm, SemesterForm, UserForm, ContributorFormSet
from evap.fsr.importers import ExcelImporter
from evap.fsr.models import EmailTemplate
from evap.fsr.tools import custom_redirect
from evap.student.forms import QuestionsForm

import random

@fsr_required
def index(request):
    semesters = Semester.objects.all()
    questionnaires = Questionnaire.objects.filter(obsolete=False)
    templates = EmailTemplate.objects.all()
    return render_to_response("fsr_index.html", dict(semesters=semesters,
                                                     questionnaires=questionnaires,
                                                     templates=templates,
                                                     disable_breadcrumb_fsr=True), context_instance=RequestContext(request))


@fsr_required
def semester_view(request, semester_id):
    semester = get_object_or_404(Semester, id=semester_id)
    try:
        tab = int(request.GET.get('tab', '1'))
    except:
        tab = 1
    
    courses = semester.course_set.all()    
    courses_by_state = []
    for state in STATES_ORDERED.keys():
        this_courses = [course for course in courses if course.state == state]
        courses_by_state.append((state, this_courses))
    
    return render_to_response("fsr_semester_view.html", dict(semester=semester, courses_by_state=courses_by_state, disable_breadcrumb_semester=True, tab=tab), context_instance=RequestContext(request))


@fsr_required
def semester_create(request):
    form = SemesterForm(request.POST or None)
    
    if form.is_valid():
        s = form.save()
        
        messages.add_message(request, messages.INFO, _("Successfully created semester."))
        return redirect('evap.fsr.views.semester_view', s.id)
    else:
        return render_to_response("fsr_semester_form.html", dict(form=form), context_instance=RequestContext(request))


@fsr_required
def semester_edit(request, semester_id):
    semester = get_object_or_404(Semester, id=semester_id)
    form = SemesterForm(request.POST or None, instance=semester)
    
    if form.is_valid():
        s = form.save()
        
        messages.add_message(request, messages.INFO, _("Successfully updated semester."))
        return redirect('evap.fsr.views.semester_view', s.id)
    else:
        return render_to_response("fsr_semester_form.html", dict(semester=semester, form=form), context_instance=RequestContext(request))


@fsr_required
def semester_delete(request, semester_id):
    semester = get_object_or_404(Semester, id=semester_id)

    if semester.can_fsr_delete:
        if request.method == 'POST':
            semester.delete()
            return redirect('fsr_root')
        else:
            return render_to_response("fsr_semester_delete.html", dict(semester=semester), context_instance=RequestContext(request))
    else:
        messages.add_message(request, messages.ERROR, _("The semester '%s' cannot be deleted, because it is still in use.") % semester.name)
        return redirect('fsr_root')


@fsr_required
def semester_publish(request, semester_id):
    semester = get_object_or_404(Semester, id=semester_id)
    courses = semester.course_set.filter(state="reviewed").all()
    
    forms = helper_create_grouped_course_selection_forms(courses, None, request)
    
    valid = helper_are_course_selection_forms_valid(forms)
    
    if valid:
        selected_courses = []
        for form in forms:
            for course in form.selected_courses:
                course.publish()
                course.save()
                selected_courses.append(course)
        
        try:
            EmailTemplate.get_publish_template().send_courses(selected_courses, True, True, True)
        except:
            messages.add_message(request, messages.WARNING, _("Could not send emails to participants and contributors"))
        messages.add_message(request, messages.INFO, _("Successfully published %d courses.") % (len(selected_courses)))
        return redirect('evap.fsr.views.semester_view', semester_id)
    else:
        return render_to_response("fsr_semester_publish.html", dict(semester=semester, forms=forms), context_instance=RequestContext(request))


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
        return redirect('evap.fsr.views.semester_view', semester_id)
    else:
        return render_to_response("fsr_import.html", dict(semester=semester, form=form), context_instance=RequestContext(request))


@fsr_required
def semester_assign_questionnaires(request, semester_id):
    semester = get_object_or_404(Semester, id=semester_id)
    form = QuestionnairesAssignForm(request.POST or None, semester=semester)
    
    if form.is_valid():
        for course in semester.course_set.filter(state__in=['prepared', 'lecturerApproved', 'new', 'approved']):
            if form.cleaned_data[course.kind]:
                course.general_contribution.questionnaires = form.cleaned_data[course.kind]
            course.save()
        
        messages.add_message(request, messages.INFO, _("Successfully assigned questionnaires."))
        return redirect('evap.fsr.views.semester_view', semester_id)
    else:
        return render_to_response("fsr_semester_assign_questionnaires.html", dict(semester=semester, form=form), context_instance=RequestContext(request))


@fsr_required
def semester_approve(request, semester_id):
    semester = get_object_or_404(Semester, id=semester_id)
    courses = semester.course_set.filter(state__in=['new', 'prepared', 'lecturerApproved']).all()

    forms = helper_create_grouped_course_selection_forms(courses, lambda course: not course.warnings(), request)
    
    valid = helper_are_course_selection_forms_valid(forms)
    
    if valid:
        count = 0
        for form in forms:
            for course in form.selected_courses:
                course.fsr_approve()
                course.save()
            count += len(form.selected_courses)
        messages.add_message(request, messages.INFO, _("Successfully approved %d courses.") % (count))
        return redirect('evap.fsr.views.semester_view', semester_id)
    else:
        return render_to_response("fsr_semester_approve.html", dict(semester=semester, forms=forms), context_instance=RequestContext(request))


@fsr_required
def semester_contributor_ready(request, semester_id):
    semester = get_object_or_404(Semester, id=semester_id)
    courses = semester.course_set.filter(state__in=['new', 'lecturerApproved']).all()
    
    forms = helper_create_grouped_course_selection_forms(courses, lambda course: not course.warnings(), request)
    
    valid = helper_are_course_selection_forms_valid(forms)
    
    if valid:
        selected_courses = []
        for form in forms:
            for course in form.selected_courses:
                course.ready_for_contributors(False)
                course.save()
                selected_courses.append(course)
        
        EmailTemplate.get_review_template().send_courses(selected_courses, True, False, False)
        
        messages.add_message(request, messages.INFO, _("Successfully marked %d courses as ready for lecturer review.") % (len(selected_courses)))
        return redirect('evap.fsr.views.semester_view', semester_id)
    else:
        return render_to_response("fsr_semester_contributor_ready.html", dict(semester=semester, forms=forms), context_instance=RequestContext(request))


@fsr_required
def semester_lottery(request, semester_id):
    semester = get_object_or_404(Semester, id=semester_id)
    
    form = LotteryForm(request.POST or None)
    
    if form.is_valid():
        eligible = []
        
        # find all users who have voted on all of their courses
        for user in User.objects.all():
            courses = user.course_set.filter(semester=semester)
            if not courses.exists():
                # user was not enrolled in any course in this semester
                continue
            if not courses.exclude(voters=user).exists():
                eligible.append(user)
        
        winners = random.sample(eligible,
                                min([form.cleaned_data['number_of_winners'], len(eligible)]))
    else:
        eligible = None
        winners = None
    
    return render_to_response("fsr_semester_lottery.html", dict(semester=semester, form=form, eligible=eligible, winners=winners), context_instance=RequestContext(request))


@fsr_required
def course_create(request, semester_id):
    semester = get_object_or_404(Semester, id=semester_id)
    course = Course(semester=semester)
    ContributionFormset = inlineformset_factory(Course, Contribution, formset=ContributorFormSet, form=ContributionForm, extra=1, exclude=('course',))
    
    form = CourseForm(request.POST or None, instance=course)
    formset = ContributionFormset(request.POST or None, instance=course)
    
    if form.is_valid() and formset.is_valid():
        form.save(user=request.user)
        formset.save()

        messages.add_message(request, messages.INFO, _("Successfully created course."))
        return redirect('evap.fsr.views.semester_view', semester_id)
    else:
        return render_to_response("fsr_course_form.html", dict(semester=semester, form=form, formset=formset), context_instance=RequestContext(request))


@fsr_required
def course_edit(request, semester_id, course_id):
    semester = get_object_or_404(Semester, id=semester_id)
    course = get_object_or_404(Course, id=course_id)
    ContributionFormset = inlineformset_factory(Course, Contribution, formset=ContributorFormSet, form=ContributionForm, extra=1, exclude=('course',))
    
    # check course state
    if not course.can_fsr_edit():
        messages.add_message(request, messages.ERROR, _("Editting not possible in current state."))
        return redirect('evap.fsr.views.semester_view', semester_id)
    
    form = CourseForm(request.POST or None, instance=course)
    formset = ContributionFormset(request.POST or None, instance=course, queryset=course.contributions.exclude(contributor=None))

    if form.is_valid() and formset.is_valid():
        form.save(user=request.user)
        formset.save()
        
        messages.add_message(request, messages.INFO, _("Successfully updated course."))
        return custom_redirect('evap.fsr.views.semester_view', semester_id, tab=request.GET.get('tab', '1'))
    else:
        return render_to_response("fsr_course_form.html", dict(semester=semester, course=course, form=form, formset=formset), context_instance=RequestContext(request))


@fsr_required
def course_delete(request, semester_id, course_id):
    semester = get_object_or_404(Semester, id=semester_id)
    course = get_object_or_404(Course, id=course_id)
    
    # check course state
    if not course.can_fsr_delete():
        messages.add_message(request, messages.ERROR, _("The course '%s' cannot be deleted, because it is still in use.") % course.name)
        return redirect('evap.fsr.views.semester_view', semester_id)
    
    if request.method == 'POST':
        course.delete()
        return custom_redirect('evap.fsr.views.semester_view', semester_id, tab=request.GET.get('tab', '1'))
    else:
        return render_to_response("fsr_course_delete.html", dict(semester=semester, course=course), context_instance=RequestContext(request))


@fsr_required
def course_review(request, semester_id, course_id, offset=None):
    semester = get_object_or_404(Semester, id=semester_id)
    course = get_object_or_404(Course, id=course_id)
    
    # check course state
    if not course.can_fsr_review():
        messages.add_message(request, messages.ERROR, _("Reviewing not possible in current state."))
        return redirect('evap.fsr.views.semester_view', semester_id)
    
    reviewFS = modelformset_factory(TextAnswer, form=ReviewTextAnswerForm, can_order=False, can_delete=False, extra=0)
    
    # compute base queryset
    base_queryset = course.textanswer_set.filter(checked=False).values_list('id', flat=True).order_by('id')
    
    # figure out offset
    if offset is None:
        # get offset for current course
        key_name = "course_%d_offset" % course.id
        offset = cache.get(key_name) or 0
        
        # store offset for next page view
        cache.set(key_name, (offset + TextAnswer.elements_per_page) % base_queryset.count())
    else:
        offset = int(offset)
    
    # compute form queryset
    length = min(TextAnswer.elements_per_page, len(base_queryset))
    form_queryset = course.textanswer_set.filter(pk__in=[base_queryset[(offset + i) % len(base_queryset)] for i in range(0, length)])
        
    # create formset from sliced queryset
    formset = reviewFS(request.POST or None, queryset=form_queryset)
    
    if formset.is_valid():
        count = 0
        for form in formset:
            form.instance.save()
            if form.instance.checked:
                count = count + 1
        
        if course.state=="evaluated" and course.is_fully_checked():
            messages.add_message(request, messages.INFO, _("Successfully reviewed %(number)d course answers for %(name)s. %(name)s is now fully reviewed.") % {'number': count, 'name': course.name} )
            course.review_finished()
            course.save()
            return custom_redirect('evap.fsr.views.semester_view', semester_id, tab=request.GET.get('tab', '1'))
        else:
            messages.add_message(request, messages.INFO, _("Successfully reviewed %(number)d course answers for %(name)s.") % {'number': count, 'name': course.name} )
            operation = request.POST.get('operation')
            
            if operation == 'save_and_next' and not course.is_fully_checked():
                return custom_redirect('evap.fsr.views.course_review', semester_id, course_id, tab=request.GET.get('tab', '1'))
            else:
                return custom_redirect('evap.fsr.views.semester_view', semester_id, tab=request.GET.get('tab', '1'))
    else:
        return render_to_response("fsr_course_review.html", dict(semester=semester, course=course, formset=formset, offset=offset, TextAnswer=TextAnswer), context_instance=RequestContext(request))


@fsr_required
def course_email(request, semester_id, course_id):
    semester = get_object_or_404(Semester, id=semester_id)
    course = get_object_or_404(Course, id=course_id)
    form = CourseEmailForm(request.POST or None, instance=course)
    
    if form.is_valid():
        form.send()
        
        if form.all_recepients_reachable():
            messages.add_message(request, messages.INFO, _("Successfully sent email to all participants/editors of '%s'.") % course.name)
        else:
            messages.add_message(request, messages.WARNING, _("Successfully sent email to many participants/editors of '%(course)s', but %(count)d could not be reached as they do not have an email address.") % dict(course=course.name, count=form.missing_email_addresses()))
        return custom_redirect('evap.fsr.views.semester_view', semester_id, tab=request.GET.get('tab', '1'))
    else:
        return render_to_response("fsr_course_email.html", dict(semester=semester, course=course, form=form), context_instance=RequestContext(request))


@fsr_required
def course_contributor_ready(request, semester_id, course_id):
    get_object_or_404(Semester, id=semester_id)
    course = get_object_or_404(Course, id=course_id)
    
    course.ready_for_contributors()
    course.save()
    
    return custom_redirect('evap.fsr.views.semester_view', semester_id, tab=request.GET.get('tab', '1'))


@fsr_required
def course_unpublish(request, semester_id, course_id):
    semester = get_object_or_404(Semester, id=semester_id)
    course = get_object_or_404(Course, id=course_id)
    
    # check course state
    if not course.state == "published":
        messages.add_message(request, messages.ERROR, _("The course '%s' cannot be unpublished, because it is not published.") % course.name)
        return custom_redirect('evap.fsr.views.semester_view', semester_id, tab=request.GET.get('tab', '1'))
    
    if request.method == 'POST':
        course.revoke()
        course.save()
        return custom_redirect('evap.fsr.views.semester_view', semester_id, tab=request.GET.get('tab', '1'))
    else:
        return render_to_response("fsr_course_unpublish.html", dict(semester=semester, course=course), context_instance=RequestContext(request))


@fsr_required
def course_comments(request, semester_id, course_id):
    semester = get_object_or_404(Semester, id=semester_id)
    course = get_object_or_404(Course, id=course_id)
    
    textanswers = course.textanswer_set.filter(checked=True)
    
    textanswers_by_question = []
    for question_id in textanswers.values_list("question", flat=True).distinct():
        textanswers_by_question.append((get_object_or_404(Question, id=question_id), textanswers.filter(question=question_id)))
    
    return render_to_response("fsr_course_comments.html", dict(semester=semester, course=course, textanswers_by_question=textanswers_by_question), context_instance=RequestContext(request))

@fsr_required
def course_preview(request, semester_id, course_id):
    semester = get_object_or_404(Semester, id=semester_id)
    course = get_object_or_404(Course, id=course_id)

    # build forms
    forms = SortedDict()
    for questionnaire, contribution in questionnaires_and_contributions(course):
        form = QuestionsForm(request.POST or None, contribution=contribution, questionnaire=questionnaire)
        forms[(contribution, questionnaire)] = form
    return render_to_response("fsr_course_preview.html", dict(forms=forms.values(), course=course, semester=semester), context_instance=RequestContext(request))


@fsr_required
def questionnaire_index(request):
    questionnaires = Questionnaire.objects.all()
    return render_to_response("fsr_questionnaire_index.html", dict(questionnaires=questionnaires), context_instance=RequestContext(request))


@fsr_required
def questionnaire_view(request, questionnaire_id):
    questionnaire = get_object_or_404(Questionnaire, id=questionnaire_id)
    
    # build forms
    contribution = Contribution(contributor=request.user)
    form = QuestionsForm(request.POST or None, contribution=contribution, questionnaire=questionnaire)
    
    return render_to_response("fsr_questionnaire_view.html", dict(forms=[form], questionnaire=questionnaire), context_instance=RequestContext(request))


@fsr_required
def questionnaire_create(request):
    questionnaire = Questionnaire()
    QuestionFormset = inlineformset_factory(Questionnaire, Question, formset=AtLeastOneFormSet, form=QuestionForm, extra=1, exclude=('questionnaire',))

    form = QuestionnaireForm(request.POST or None, instance=questionnaire)
    formset = QuestionFormset(request.POST or None, instance=questionnaire)
    
    if form.is_valid() and formset.is_valid():
        form.save()
        formset.save()
        
        messages.add_message(request, messages.INFO, _("Successfully created questionnaire."))
        return redirect('evap.fsr.views.questionnaire_index')
    else:
        return render_to_response("fsr_questionnaire_form.html", dict(form=form, formset=formset), context_instance=RequestContext(request))


@fsr_required
def questionnaire_edit(request, questionnaire_id):
    questionnaire = get_object_or_404(Questionnaire, id=questionnaire_id)
    QuestionFormset = inlineformset_factory(Questionnaire, Question, formset=AtLeastOneFormSet, form=QuestionForm, extra=1, exclude=('questionnaire',))
    
    form = QuestionnaireForm(request.POST or None, instance=questionnaire)
    formset = QuestionFormset(request.POST or None, instance=questionnaire)
    
    if questionnaire.obsolete:
        messages.add_message(request, messages.INFO, _("Obsolete questionnaires cannot be edited."))
        return redirect('evap.fsr.views.questionnaire_index')
    
    if form.is_valid() and formset.is_valid():
        form.save()
        formset.save()
        
        messages.add_message(request, messages.INFO, _("Successfully updated questionnaire."))
        return redirect('evap.fsr.views.questionnaire_index')
    else:
        return render_to_response("fsr_questionnaire_form.html", dict(questionnaire=questionnaire, form=form, formset=formset), context_instance=RequestContext(request))


@fsr_required
def questionnaire_copy(request, questionnaire_id):
    if request.method == "POST":
        questionnaire = Questionnaire()
        QuestionFormset = inlineformset_factory(Questionnaire, Question, formset=AtLeastOneFormSet, form=QuestionForm, extra=1, exclude=('questionnaire',))
        
        form = QuestionnaireForm(request.POST, instance=questionnaire)
        formset = QuestionFormset(request.POST.copy(), instance=questionnaire, save_as_new=True)
        
        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            
            messages.add_message(request, messages.INFO, _("Successfully created questionnaire."))
            return redirect('evap.fsr.views.questionnaire_index')
        else:
            return render_to_response("fsr_questionnaire_form.html", dict(form=form, formset=formset), context_instance=RequestContext(request))
    else:
        questionnaire = get_object_or_404(Questionnaire, id=questionnaire_id)
        QuestionFormset = inlineformset_factory(Questionnaire, Question, formset=IdLessQuestionFormSet, form=QuestionForm, extra=1, exclude=('questionnaire',))
        
        form = QuestionnaireForm(instance=questionnaire)
        formset = QuestionFormset(instance=Questionnaire(), queryset=questionnaire.question_set.all())
        
        return render_to_response("fsr_questionnaire_form.html", dict(form=form, formset=formset), context_instance=RequestContext(request))


@fsr_required
def questionnaire_delete(request, questionnaire_id):
    questionnaire = get_object_or_404(Questionnaire, id=questionnaire_id)
    
    if questionnaire.can_fsr_delete:
        if request.method == 'POST':
            questionnaire.delete()
            return redirect('evap.fsr.views.questionnaire_index')
        else:
            return render_to_response("fsr_questionnaire_delete.html", dict(questionnaire=questionnaire), context_instance=RequestContext(request))
    else:
        messages.add_message(request, messages.ERROR, _("The questionnaire '%s' cannot be deleted, because it is still in use.") % questionnaire.name)
        return redirect('evap.fsr.views.questionnaire_index')


@fsr_required
def user_index(request):
    users = User.objects.order_by("last_name", "first_name", "username")
    
    filter = request.GET.get('filter')
    if filter == "fsr":
        users = users.filter(is_staff=True)
    elif filter == "responsibles":
        users = [user for user in users if UserProfile.get_for_user(user).is_responsible]
    elif filter == "delegates":
        users = [user for user in users if UserProfile.get_for_user(user).is_delegate]
    
    return render_to_response("fsr_user_index.html", dict(users=users, filter=filter), context_instance=RequestContext(request))


@fsr_required
def user_create(request):
    profile = UserProfile(user=User())
    form = UserForm(request.POST or None, instance=profile)
    
    if form.is_valid():
        #profile.user.save()
        form.save()
        
        messages.add_message(request, messages.INFO, _("Successfully created user."))
        
        if "filter" in request.GET:
            return custom_redirect('evap.fsr.views.user_index', filter=request.GET['filter'])
        else:
            return redirect('evap.fsr.views.user_index')
    else:
        return render_to_response("fsr_user_form.html", dict(form=form), context_instance=RequestContext(request))


@fsr_required
def user_edit(request, user_id):
    user = get_object_or_404(User, id=user_id)
    form = UserForm(request.POST or None, request.FILES or None, instance=UserProfile.get_for_user(user))
    
    if form.is_valid():
        form.save()
        
        messages.add_message(request, messages.INFO, _("Successfully updated user."))
        
        if "filter" in request.GET:
            return custom_redirect('evap.fsr.views.user_index', filter=request.GET['filter'])
        else:
            return redirect('evap.fsr.views.user_index')
    else:
        return render_to_response("fsr_user_form.html", dict(form=form, object=user), context_instance=RequestContext(request))


@fsr_required
def user_delete(request, user_id):
    user = get_object_or_404(User, id=user_id)
    
    if UserProfile.get_for_user(user).can_fsr_delete:
        if request.method == 'POST':
            user.delete()
            return redirect('evap.fsr.views.user_index')
        else:
            return render_to_response("fsr_user_delete.html", dict(user=user), context_instance=RequestContext(request))
    else:
        messages.add_message(request, messages.ERROR, _("The user '%s' cannot be deleted, because he lectures courses.") % UserProfile.get_for_user(user).full_name)
        return redirect('evap.fsr.views.user_index')


@fsr_required
def template_edit(request, template_id):
    template = get_object_or_404(EmailTemplate, id=template_id)
    form = EmailTemplateForm(request.POST or None, request.FILES or None, instance=template)
    
    if form.is_valid():
        form.save()
        
        messages.add_message(request, messages.INFO, _("Successfully updated template."))
        return redirect('fsr_root')
    else:
        return render_to_response("fsr_template_form.html", dict(form=form, template=template), context_instance=RequestContext(request))


def helper_create_grouped_course_selection_forms(courses, filter_func, request):
    grouped_courses = {}
    for course in courses:
        degree = course.degree
        if not grouped_courses.has_key(degree):
            grouped_courses[degree] = []
        grouped_courses[degree].append(course)
    
    forms = []
    for degree, degreeCourses in grouped_courses.items():
        form = SelectCourseForm(degree, degreeCourses, filter_func, request.POST or None)
        forms.append(form)
    
    return forms


def helper_are_course_selection_forms_valid(forms):
    valid = True
    for form in forms:
        if not form.is_valid():
            valid = False
    return valid
