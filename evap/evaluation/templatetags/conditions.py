from django.template import Library, Node
from django.template.context import Context
from django.template.loader import get_template
from django.utils.importlib import import_module

register = Library()

class IfLecturerNode(Node):
    def __init__(self, nodelist, course_or_semester_val):
        self.nodelist = nodelist
        self.course_or_semester_val = course_or_semester_val
    
    def render(self, context):
        current_user = context['user']
        course_or_semester = self.course_or_semester_val.resolve(context, True)
        if course_or_semester.is_user_lecturer(current_user):
            return self.nodelist.render(context)
        else:
            return ''

@register.tag('if_lecturer')
def do_if_lecturer(parser, token):
    bits = list(token.split_contents())
    if len(bits) != 2:
        raise TemplateSyntaxError("%r takes one argument" % bits[0])
    
    nodelist = parser.parse(('endif_lecturer',))
    parser.delete_first_token()
    
    val1 = parser.compile_filter(bits[1])
    return IfLecturerNode(nodelist, val1)

