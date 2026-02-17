from django.http import HttpResponseBadRequest
from django.views.decorators.http import require_POST

from evap.cms.models import CourseLink, EvaluationLink, IgnoredEvaluation
from evap.evaluation.auth import manager_required
from evap.evaluation.tools import (
    HttpResponseNoContent,
    get_object_from_dict_pk_entry_or_logged_40x,
)


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
def cms_course_link_update_activation(request):
    cms_course_link = get_object_from_dict_pk_entry_or_logged_40x(CourseLink, request.POST, "cms_course_link_id")

    is_active_bool_string = request.POST.get("is_active", None)
    if is_active_bool_string not in ["true", "false"]:
        return HttpResponseBadRequest()

    cms_course_link.is_active = is_active_bool_string == "true"
    cms_course_link.save()

    return HttpResponseNoContent()


@require_POST
@manager_required
def cms_evaluation_link_update_activation(request):
    cms_evaluation_link = get_object_from_dict_pk_entry_or_logged_40x(
        EvaluationLink, request.POST, "cms_evaluation_link_id"
    )

    is_active_bool_string = request.POST.get("is_active", None)
    if is_active_bool_string not in ["true", "false"]:
        return HttpResponseBadRequest()

    cms_evaluation_link.is_active = is_active_bool_string == "true"
    cms_evaluation_link.save()

    return HttpResponseNoContent()
