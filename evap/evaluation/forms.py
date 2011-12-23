from django import forms
from django.template import Template, Context
from django.utils.html import escape
from django.utils.safestring import mark_safe
from django.utils.translation import ugettext_lazy as _


class NewKeyForm(forms.Form):
    email = forms.EmailField(label=_(u"e-mail address"))


class BootstrapFieldset(object):
    """ Fieldset container. Renders to a <fieldset>. """
    
    def __init__(self, legend, *fields):
        self.legend_html = legend and ('<legend>%s</legend>' % legend) or ''
        self.fields = fields
    
    def as_html(self, form):
        return u'<fieldset>%s%s</fieldset>' % (self.legend_html, form.render_fields(self.fields), )


class BootstrapMixin(object):
    """"""
    
    __TEMPLATE = """<div class="clearfix{% if errors %} error{% endif %}">""" \
                 """{{ label }}<div class="input">""" \
                 """{{ bf }}""" \
                 """{% if errors %}<span class="help-inline">{{ errors }}</span>{% endif %}""" \
                 """{% if help_text %}<span class="help-block">{{ help_text }}</span>{% endif %}""" \
                 """</div></div>"""
    
    def as_div(self):
        """ Render the form as a set of <div>s. """
        
        top_errors = []
        output = self.__render_fields(self.__layout, top_errors)
        
        if top_errors:
            errors = error_list(top_errors)
        else:
            errors = u''
        
        return mark_safe(errors + output)
    
    @property
    def __layout(self):
        try:
            return self.__layout_store
        except AttributeError:
            self.__layout_store = self.fields.keys()
            return self.__layout_store
    
    @property
    def __custom_fields(self):
        try:
            return self.__custom_fields_store
        except AttributeError:
            self.__custom_fields_store = {}
            return self.__custom_fields_store
    
    def __render_fields(self, fields, top_errors, separator=u""):
        """ Render a list of fields and join the fields by the value in separator. """
        
        output = []
        
        for field in fields:
            if isinstance(field, BootstrapFieldset):
                output.append(field.as_html(self))
            else:
                output.append(self.__render_field(field, top_errors))
        
        return separator.join(output)
    
    def __render_field(self, field, top_errors):
        """ Render a named field to HTML. """
        
        try:
            field_instance = self.fields[field]
        except KeyError:
            raise Exception("Could not resolve form field '%s'." % field)
        
        bf = forms.forms.BoundField(self, field_instance, field)
        
        output = ''
        
        if bf.errors:
            # If the field contains errors, render the errors to a <ul>
            # using the error_list helper function.
            # bf_errors = error_list([escape(error) for error in bf.errors])
            bf_errors = ', '.join([e for e in bf.errors])
        else:
            bf_errors = ''
        
        if bf.is_hidden:
            # If the field is hidden, add it at the top of the form
            # self.prefix.append(unicode(bf))
            # If the hidden field has errors, append them to the top_errors
            # list which will be printed out at the top of form
            if bf_errors:
                top_errors.extend(bf.errors)
        
        else:
            # Find field + widget type css classes
            css_class = type(field_instance).__name__ + " " + type(field_instance.widget).__name__
            
            # Add an extra class, Required, if applicable
            if field_instance.required:
                css_class += " required"
            
            if field_instance.help_text:
                # The field has a help_text, construct <span> tag
                help_text = '<span class="help_text">%s</span>' % escape(field_instance.help_text)
            else:
                help_text = u''
            
            field_hash = {
                'class' : mark_safe(css_class),
                'label' : mark_safe(bf.label and bf.label_tag(bf.label) or ''),
                'help_text' :mark_safe(help_text),
                'field' : field_instance,
                'bf' : mark_safe(unicode(bf)),
                'bf_raw' : bf,
                'errors' : mark_safe(bf_errors),
                'field_type' : mark_safe(field.__class__.__name__),
            }
            
            output = Template(self.__TEMPLATE).render(Context(field_hash))
        
        return mark_safe(output)
