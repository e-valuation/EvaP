from django.views.decorators.http import require_POST

from evap.cms.models import IgnoredEvaluation
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
