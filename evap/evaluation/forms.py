from itertools import chain

from django import forms
from django.contrib.auth import authenticate
from django.forms import widgets
from django.forms.models import ModelChoiceIterator
from django.template import Template, Context
from django.utils.encoding import force_text
from django.utils.html import escape, conditional_escape
from django.utils.safestring import mark_safe
from django.utils.translation import ugettext_lazy as _
from django.views.decorators.debug import sensitive_variables

from evap.evaluation.models import UserProfile


class QuestionnaireChoiceIterator(ModelChoiceIterator):
    def choice(self, obj):
        return (self.field.prepare_value(obj), self.field.label_from_instance(obj), obj.description)


class QuestionnaireSelectMultiple(forms.CheckboxSelectMultiple):
    def render(self, name, value, attrs=None, choices=()):
        if value is None:
            value = []
        has_id = attrs and 'id' in attrs
        final_attrs = self.build_attrs(attrs, name=name)
        output = ['<ul class="inputs-list">']

        # Normalize to strings
        str_values = set([force_text(v) for v in value])
        for i, (option_value, option_label, option_text) in enumerate(chain(self.choices, choices)):
            # If an ID attribute was given, add a numeric index as a suffix,
            # so that the checkboxes don't all have the same ID attribute.
            if has_id:
                final_attrs = dict(final_attrs, id='%s_%s' % (attrs['id'], i))
                label_for = ' for="%s"' % final_attrs['id']
            else:
                label_for = ''

            checkbox = widgets.CheckboxInput(final_attrs, check_test=lambda value: value in str_values)
            option_value = force_text(option_value)
            rendered_checkbox = checkbox.render(name, option_value)
            option_label = conditional_escape(force_text(option_label))
            output.append('<li data-toggle="tooltip" data-placement="left" title="{}"><div class="checkbox"><label{}>{} {}</label></div></li>'.format(
                escape(option_text), label_for, rendered_checkbox.replace('class="form-control"', ''), option_label))
        output.append('</ul>')
        return mark_safe('\n'.join(output))


class QuestionnaireMultipleChoiceField(forms.ModelMultipleChoiceField):
    widget = QuestionnaireSelectMultiple

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.help_text = ""

    def _get_choices(self):
        # If self._choices is set, then somebody must have manually set
        # the property self.choices. In this case, just return self._choices.
        if hasattr(self, '_choices'):
            return self._choices

        # Otherwise, execute the QuerySet in self.queryset to determine the
        # choices dynamically. Return a fresh ModelChoiceIterator that has not been
        # consumed. Note that we're instantiating a new ModelChoiceIterator *each*
        # time _get_choices() is called (and, thus, each time self.choices is
        # accessed) so that we can ensure the QuerySet has not been consumed. This
        # construct might look complicated but it allows for lazy evaluation of
        # the queryset.
        return QuestionnaireChoiceIterator(self)
    choices = property(_get_choices, forms.ChoiceField._set_choices)


class LoginUsernameForm(forms.Form):
    """Form encapsulating the login with username and password, for example from an Active Directory.
    """

    username = forms.CharField(label=_("Username"), max_length=254)
    password = forms.CharField(label=_("Password"), widget=forms.PasswordInput)

    def __init__(self, request=None, *args, **kwargs):
        """
        If request is passed in, the form will validate that cookies are
        enabled. Note that the request (a HttpRequest object) must have set a
        cookie with the key TEST_COOKIE_NAME and value TEST_COOKIE_VALUE before
        running this validation.
        """
        self.request = request
        self.user_cache = None
        super().__init__(*args, **kwargs)

    @sensitive_variables('password')
    def clean_password(self):
        username = self.cleaned_data.get('username')
        password = self.cleaned_data.get('password')

        if username and password:
            self.user_cache = authenticate(username=username, password=password)
            if self.user_cache is None:
                raise forms.ValidationError(_("Please enter a correct username and password."))
        self.check_for_test_cookie()
        return password

    def check_for_test_cookie(self):
        if self.request and not self.request.session.test_cookie_worked():
            raise forms.ValidationError(_("Your Web browser doesn't appear to have cookies enabled. Cookies are required for logging in."))

    def get_user_id(self):
        if self.user_cache:
            return self.user_cache.id
        return None

    def get_user(self):
        return self.user_cache


class NewKeyForm(forms.Form):
    email = forms.EmailField(label=_("Email address"))

    def __init__(self, *args, **kwargs):
        self.user_cache = None

        super().__init__(*args, **kwargs)

    def clean_email(self):
        email = self.cleaned_data.get('email')

        if not UserProfile.email_needs_login_key(email):
            raise forms.ValidationError(_("HPI users cannot request login keys. Please login using your domain credentials."))

        try:
            user = UserProfile.objects.get(email__iexact=email)
            self.user_cache = user
        except UserProfile.DoesNotExist:
            raise forms.ValidationError(_("No user with this email address was found. Please make sure to enter the email address already known to the university office."))

        return email

    def get_user(self):
        return self.user_cache


class BootstrapFieldset(object):
    """ Fieldset container. Renders to a <fieldset>. """

    def __init__(self, legend, *fields):
        self.legend_html = legend and ('<legend>%s</legend>' % legend) or ''
        self.fields = fields

    def as_html(self, form):
        return '<fieldset>%s%s</fieldset>' % (self.legend_html, form.render_fields(self.fields), )


# taken from https://github.com/earle/django-bootstrap/blob/master/bootstrap/forms.py
class BootstrapMixin(object):

    __TEMPLATE = """<div class="form-group{% if errors %} has-error{% endif %}">
                 <label class="col-sm-2 control-label" for="{{ field_id }}">{{ label }}</label>
                 <div class="col-sm-6">
                 {{ bf }}
                 {% if errors %}<span class="help-block">{{ errors }}</span>{% endif %}
                 {% if help_text %}<span class="help-block">{{ help_text }}</span>{% endif %}
                 </div></div>"""

    def as_div(self):
        """ Render the form as a set of <div>s. """

        top_errors = []
        self.prefix_fields = []
        output = self.__render_fields(self.__layout, top_errors)

        top_errors.extend(self.non_field_errors())

        if top_errors:
            errors = """<ul class="errorlist"><li>%s</li></ul>""" % "</li><li>".join(top_errors)
        else:
            errors = ""

        prefix = ''.join(self.prefix_fields)

        return mark_safe(prefix + errors + output)

    @property
    def __layout(self):
        try:
            return self.__layout_store
        except AttributeError:
            self.__layout_store = list(self.fields.keys())
            return self.__layout_store

    @property
    def __custom_fields(self):
        try:
            return self.__custom_fields_store
        except AttributeError:
            self.__custom_fields_store = {}
            return self.__custom_fields_store

    def __render_fields(self, fields, top_errors, separator=""):
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
            self.prefix_fields.append(str(bf))
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
                help_text = escape(str(field_instance.help_text))
            else:
                help_text = ''

            field_id = "id_" + bf.name
            attrs = {"id": field_id}

            if isinstance(field_instance.widget, (widgets.DateInput, widgets.Textarea, widgets.TextInput, widgets.SelectMultiple, widgets.Select)):
                attrs['class'] = 'form-control'

            if isinstance(field_instance.widget, widgets.DateInput) and field_instance.disabled is False:
                attrs['data-datepicker'] = "datepicker"

            field_hash = {
                'class': mark_safe(css_class),
                'label': mark_safe(bf.label or ''),
                'help_text': mark_safe(str(help_text)),
                'field': field_instance,
                'field_id': field_id,
                'bf': mark_safe(str(bf.as_widget(attrs=attrs))),
                'bf_raw': bf,
                'errors': mark_safe(bf_errors),
                'field_type': mark_safe(field.__class__.__name__),
            }

            output = Template(self.__TEMPLATE).render(Context(field_hash))

        return mark_safe(output)
