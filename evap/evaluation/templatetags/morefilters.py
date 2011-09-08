from django.template import Library

register = Library()

# from http://www.jongales.com/blog/2009/10/19/percentage-django-template-tag/
@register.filter(name='percentage')  
def percentage(fraction, population):  
    try:  
        return "%.0f%%" % ((float(fraction) / float(population)) * 100)  
    except ValueError:  
        return ''
