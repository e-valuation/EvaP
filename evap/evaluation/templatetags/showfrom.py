from django.template import Library
from django.template.context import Context
from django.template.loader import get_template
from django.utils.importlib import import_module

register = Library()

@register.simple_tag(takes_context=True)
def show_from(context, source, template_name):
    module, dot, function = source.rpartition(".")
    args = getattr(import_module(module), function)()
    try:
        context.push()
        context.update(args)
        return get_template(template_name).render(context)
    finally:
        context.pop()
