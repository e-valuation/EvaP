from django import forms

class UserModelMultipleChoiceField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, obj):
        if obj.get_profile():
            return obj.get_profile().full_name
        else:
            return obj.username