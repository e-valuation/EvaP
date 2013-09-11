from itertools import chain

from django import forms
from django.forms.models import ModelChoiceIterator
from django.utils.html import escape, conditional_escape
from django.utils.encoding import force_unicode

from evap.evaluation.models import UserProfile


class UserModelMultipleChoiceField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, obj):
        return UserProfile.get_for_user(obj).full_name


class ToolTipModelChoiceIterator(ModelChoiceIterator):
    def choice(self, obj):
        return (self.field.prepare_value(obj), self.field.label_from_instance(obj), self.field.title_from_instance(obj))


class ToolTipSelectMultiple(forms.SelectMultiple):
    def render_option(self, selected_choices, option_value, option_label, option_title):
        option_value = force_unicode(option_value)
        selected_html = (option_value in selected_choices) and u' selected="selected"' or ''
        return u'<option value="%s" title="%s" %s>%s</option>' % (
            escape(option_value), escape(option_title), selected_html,
            conditional_escape(force_unicode(option_label)))
    
    def render_options(self, choices, selected_choices):
        # Normalize to strings.
        selected_choices = set([force_unicode(v) for v in selected_choices])
        output = []
        for option_value, option_label, option_title in chain(self.choices, choices):
            output.append(self.render_option(selected_choices, option_value, option_label, option_title))
        return u'\n'.join(output)


class ToolTipModelMultipleChoiceField(forms.ModelMultipleChoiceField):
    widget = ToolTipSelectMultiple
    
    def title_from_instance(self, obj):
        return obj.description
    
    def _get_choices(self):
        if hasattr(self, '_choices'):
            return self._choices
        return ToolTipModelChoiceIterator(self)
    choices = property(_get_choices, forms.ChoiceField._set_choices)
