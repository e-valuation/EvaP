from django.template import Library
from evap.evaluation.models import Semester

register = Library()


@register.inclusion_tag("user_list_with_links.html")
def include_user_list_with_links(users):
    return dict(users=users)


@register.inclusion_tag("sortable_form_js.html")
def include_sortable_form_js():
    return dict()

