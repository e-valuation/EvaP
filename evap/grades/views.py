from django.shortcuts import get_object_or_404, render, redirect
from django.db.models import Prefetch
from django.core.exceptions import PermissionDenied
from django.contrib import messages
from django.conf import settings
from django.utils.translation import ugettext as _
from django.http import HttpResponse
from django.views.decorators.http import require_POST, require_GET

from sendfile import sendfile

from evap.evaluation.auth import grade_publisher_required, grade_downloader_required, grade_publisher_or_manager_required
from evap.evaluation.models import Semester, Contribution, Evaluation
from evap.grades.models import GradeDocument
from evap.grades.forms import GradeDocumentForm
from evap.evaluation.tools import send_publish_notifications


@grade_publisher_required
def index(request):
    template_data = dict(
        semesters=Semester.objects.filter(grade_documents_are_deleted=False),
        disable_breadcrumb_grades=True,
    )
    return render(request, "grades_index.html", template_data)


def prefetch_data(evaluations):
    evaluations = evaluations.prefetch_related(
        Prefetch("contributions", queryset=Contribution.objects.filter(responsible=True).select_related("contributor"), to_attr="responsible_contributions"),
        "degrees")

    evaluation_data = []
    for evaluation in evaluations:
        evaluation.responsible_contributors = [contribution.contributor for contribution in evaluation.responsible_contributions]
        evaluation_data.append((
            evaluation,
            evaluation.midterm_grade_documents.count(),
            evaluation.final_grade_documents.count()
        ))

    return evaluation_data


@grade_publisher_required
def semester_view(request, semester_id):
    semester = get_object_or_404(Semester, id=semester_id)
    if semester.grade_documents_are_deleted:
        raise PermissionDenied

    evaluations = semester.evaluations.filter(is_graded=True).exclude(state='new')
    evaluations = prefetch_data(evaluations)

    template_data = dict(
        semester=semester,
        evaluations=evaluations,
        disable_if_archived="disabled" if semester.grade_documents_are_deleted else "",
        disable_breadcrumb_semester=True,
    )
    return render(request, "grades_semester_view.html", template_data)


@grade_publisher_or_manager_required
def evaluation_view(request, semester_id, evaluation_id):
    semester = get_object_or_404(Semester, id=semester_id)
    if semester.grade_documents_are_deleted:
        raise PermissionDenied
    evaluation = get_object_or_404(Evaluation, id=evaluation_id, semester=semester)

    template_data = dict(
        semester=semester,
        evaluation=evaluation,
        grade_documents=evaluation.grade_documents.all(),
        disable_if_archived="disabled" if semester.grade_documents_are_deleted else "",
        disable_breadcrumb_evaluation=True,
    )
    return render(request, "grades_evaluation_view.html", template_data)


@grade_publisher_required
def upload_grades(request, semester_id, evaluation_id):
    semester = get_object_or_404(Semester, id=semester_id)
    if semester.grade_documents_are_deleted:
        raise PermissionDenied
    evaluation = get_object_or_404(Evaluation, id=evaluation_id, semester=semester)

    final_grades = request.GET.get('final') == 'true'  # if parameter is not given, assume midterm grades

    grade_document = GradeDocument(evaluation=evaluation)
    if final_grades:
        grade_document.type = GradeDocument.FINAL_GRADES
        grade_document.description_en = settings.DEFAULT_FINAL_GRADES_DESCRIPTION_EN
        grade_document.description_de = settings.DEFAULT_FINAL_GRADES_DESCRIPTION_DE
    else:
        grade_document.type = GradeDocument.MIDTERM_GRADES
        grade_document.description_en = settings.DEFAULT_MIDTERM_GRADES_DESCRIPTION_EN
        grade_document.description_de = settings.DEFAULT_MIDTERM_GRADES_DESCRIPTION_DE

    form = GradeDocumentForm(request.POST or None, request.FILES or None, instance=grade_document)

    if form.is_valid():
        form.save(modifying_user=request.user)
        if final_grades and evaluation.state == 'reviewed':
            evaluation.publish()
            evaluation.save()
            send_publish_notifications([evaluation])

        messages.success(request, _("Successfully uploaded grades."))
        return redirect('grades:evaluation_view', semester.id, evaluation.id)
    else:
        template_data = dict(
            semester=semester,
            evaluation=evaluation,
            form=form,
            final_grades=final_grades,
            show_automated_publishing_info=final_grades,
        )
        return render(request, "grades_upload_form.html", template_data)


@require_POST
@grade_publisher_required
def toggle_no_grades(request):
    evaluation_id = request.POST.get("evaluation_id")
    evaluation = get_object_or_404(Evaluation, id=evaluation_id)
    if evaluation.semester.grade_documents_are_deleted:
        raise PermissionDenied

    evaluation.gets_no_grade_documents = not evaluation.gets_no_grade_documents
    evaluation.save()
    if evaluation.gets_no_grade_documents:
        if evaluation.state == 'reviewed':
            evaluation.publish()
            evaluation.save()
            send_publish_notifications([evaluation])

    return HttpResponse()  # 200 OK


@require_GET
@grade_downloader_required
def download_grades(request, grade_document_id):
    grade_document = get_object_or_404(GradeDocument, id=grade_document_id)
    if grade_document.evaluation.semester.grade_documents_are_deleted:
        raise PermissionDenied

    return sendfile(request, grade_document.file.path, attachment=True, attachment_filename=grade_document.filename())


@grade_publisher_required
def edit_grades(request, semester_id, evaluation_id, grade_document_id):
    semester = get_object_or_404(Semester, id=semester_id)
    if semester.grade_documents_are_deleted:
        raise PermissionDenied
    evaluation = get_object_or_404(Evaluation, id=evaluation_id, semester=semester)
    grade_document = get_object_or_404(GradeDocument, id=grade_document_id, evaluation=evaluation)

    form = GradeDocumentForm(request.POST or None, request.FILES or None, instance=grade_document)

    if form.is_valid():
        form.save(modifying_user=request.user)
        messages.success(request, _("Successfully updated grades."))
        return redirect('grades:evaluation_view', semester.id, evaluation.id)
    else:
        template_data = dict(
            semester=semester,
            evaluation=evaluation,
            form=form,
            show_automated_publishing_info=False,
        )
        return render(request, "grades_upload_form.html", template_data)


@require_POST
@grade_publisher_required
def delete_grades(request):
    grade_document_id = request.POST.get("grade_document_id")
    grade_document = get_object_or_404(GradeDocument, id=grade_document_id)

    grade_document.delete()
    return HttpResponse()  # 200 OK
