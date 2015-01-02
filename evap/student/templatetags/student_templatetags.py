from django.template import Library

register = Library()

@register.inclusion_tag('student_vote_row.html')
def student_vote_row(field):
    return {'field': field}
