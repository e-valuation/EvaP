from django.template import Library

register = Library()


@register.filter
def text_answer_warning_trigger_strings(text_answer_warnings):
    return [text_answer_warning.trigger_strings for text_answer_warning in text_answer_warnings]
