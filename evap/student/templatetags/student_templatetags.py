from django.template import Library

register = Library()

@register.inclusion_tag('student_vote_questionnaire_group.html')
def include_student_vote_questionnaire_group(questionnaire_group, preview):
    return {
        'questionnaire_group': questionnaire_group,
        'preview': preview,
    }
