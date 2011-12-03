from django import forms
from django.utils.translation import ugettext_lazy as _


class NewKeyForm(forms.Form):
    email = forms.EmailField(label=_(u"e-mail address"))
