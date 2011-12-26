from django import template
from django.conf import settings
from django.template import Library
from evap.evaluation.tools import GRADE_NAMES

register = Library()


# from http://www.jongales.com/blog/2009/10/19/percentage-django-template-tag/
@register.filter(name='percentage')
def percentage(fraction, population):
    try:
        return "%.0f%%" % ((float(fraction) / float(population)) * 100)
    except ValueError:
        return ''


@register.filter(name='gradename')
def gradename(grade):
    return GRADE_NAMES.get(grade, "")


@register.tag
def value_from_settings(parser, token):
    try:
        # split_contents() knows not to split quoted strings.
        tag_name, var = token.split_contents()
    except ValueError:
        raise template.TemplateSyntaxError, "%r tag requires a single argument" % token.contents.split()[0]
    return ValueFromSettings(var)


class ValueFromSettings(template.Node):
    def __init__(self, var):
        super(ValueFromSettings, self).__init__()
        self.arg = template.Variable(var)
    
    def render(self, context):
        return settings.__getattr__(str(self.arg))
