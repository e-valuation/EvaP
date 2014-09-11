from django import template

register = template.Library()

@register.inclusion_tag('fsr_course_selection_list.html')
def course_list(course_forms, btn_label, empty_msg):
    return {
        'course_forms': course_forms,
        'btn_label':    btn_label,
        'empty_msg':    empty_msg
    }
