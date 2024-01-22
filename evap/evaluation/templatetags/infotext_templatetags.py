from django.template import Library

from evap.evaluation.models import Infotext

register = Library()


@register.inclusion_tag("infobox.html", takes_context=True)
def show_infotext(context, page_name):
    to_page_id = {
        "contributor_index": Infotext.Page.CONTRIBUTOR_INDEX,
        "grades_pages": Infotext.Page.GRADES_PAGES,
        "student_index": Infotext.Page.STUDENT_INDEX,
    }

    return {
        "CSP_NONCE": context["request"].csp_nonce,
        "infotext": Infotext.objects.get(page=to_page_id[page_name])
    }
