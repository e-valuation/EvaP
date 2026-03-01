from django import forms
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _

from evap.evaluation.models import Evaluation


class EvaluationMergeSelectionForm(forms.Form):
    main_evaluation = forms.ModelChoiceField(Evaluation.objects.all(), label=_("Main evaluation"))
    other_evaluation = forms.ModelChoiceField(Evaluation.objects.all(), label=_("Other evaluation"))

    def __init__(self, *args, main_evaluation_id, **kwargs):
        super().__init__(*args, **kwargs)
        main_evaluation = get_object_or_404(Evaluation, id=main_evaluation_id)
        semester_id = main_evaluation.course.semester.pk

        self.fields["main_evaluation"].queryset = Evaluation.objects.filter(course__semester__pk=semester_id).distinct()
        self.fields["main_evaluation"].initial = main_evaluation.pk
        self.fields["other_evaluation"].queryset = Evaluation.objects.filter(
            course__semester__pk=semester_id
        ).distinct()

    def clean(self):
        super().clean()
        if self.cleaned_data.get("main_evaluation") == self.cleaned_data.get("other_evaluation"):
            raise ValidationError(_("You must select two different evaluations."))
