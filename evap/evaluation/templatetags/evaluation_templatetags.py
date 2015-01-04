from django.template import Library
from evap.evaluation.models import Semester

register = Library()


@register.inclusion_tag("user_list_with_links.html")
def include_user_list_with_links(users):
    return dict(users=users)
