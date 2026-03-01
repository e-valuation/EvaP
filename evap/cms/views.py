from django.contrib import messages
from django.db import transaction
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST

from evap.cms.forms import EvaluationMergeSelectionForm
from evap.cms.models import CourseLink, EvaluationLink, IgnoredEvaluation
from evap.evaluation.auth import manager_required
from evap.evaluation.models import Evaluation
from evap.evaluation.tools import (
    HttpResponseNoContent,
    get_object_from_dict_pk_entry_or_logged_40x,
)
from evap.staff.importers import import_persons_from_evaluation
from evap.staff.tools import ImportType
from evap.staff.views import _evaluation_delete


@require_POST
@manager_required
def ignored_evaluation_delete(request):
    ignored_evaluation = get_object_from_dict_pk_entry_or_logged_40x(
        IgnoredEvaluation, request.POST, "ignored_evaluation_id"
    )
    ignored_evaluation.delete()
    return HttpResponseNoContent()


@require_POST
@manager_required
def course_link_update_activation(request):
    course_link = get_object_from_dict_pk_entry_or_logged_40x(CourseLink, request.POST, "course_link_id")

    is_active_bool_string = request.POST.get("is_active", None)
    if is_active_bool_string not in ["true", "false"]:
        return HttpResponseBadRequest()

    course_link.is_active = is_active_bool_string == "true"
    course_link.save()

    return HttpResponseNoContent()


@require_POST
@manager_required
def evaluation_link_update_activation(request):
    evaluation_link = get_object_from_dict_pk_entry_or_logged_40x(EvaluationLink, request.POST, "evaluation_link_id")

    is_active_bool_string = request.POST.get("is_active", None)
    if is_active_bool_string not in ["true", "false"]:
        return HttpResponseBadRequest()

    evaluation_link.is_active = is_active_bool_string == "true"
    evaluation_link.save()

    return HttpResponseNoContent()


@manager_required
def evaluation_merge_selection(request, main_evaluation_id):
    main_evaluation = get_object_or_404(Evaluation, id=main_evaluation_id)
    form = EvaluationMergeSelectionForm(request.POST or None, main_evaluation_id=main_evaluation.pk)

    if form.is_valid():
        main_evaluation = form.cleaned_data["main_evaluation"]
        other_evaluation = form.cleaned_data["other_evaluation"]

        with transaction.atomic():
            for evaluation_link in EvaluationLink.objects.filter(evaluation=other_evaluation):
                evaluation_link.evaluation = main_evaluation
                evaluation_link.save()

            participant_importer_log = import_persons_from_evaluation(
                ImportType.PARTICIPANT, main_evaluation, test_run=False, source_evaluation=other_evaluation
            )
            contributor_importer_log = import_persons_from_evaluation(
                ImportType.CONTRIBUTOR, main_evaluation, test_run=False, source_evaluation=other_evaluation
            )
            _evaluation_delete(request, other_evaluation)

        participant_importer_log.forward_messages_to_django(request)
        contributor_importer_log.forward_messages_to_django(request)
        messages.success(request, _("Successfully merged evaluations."))

        return redirect("staff:semester_view", main_evaluation.course.semester.id)

    return render(
        request,
        "cms_evaluation_merge_selection.html",
        {
            "form": form,
            "semester": main_evaluation.course.semester,
        },
    )
