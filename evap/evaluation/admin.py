from django.conf import settings
from django.contrib import admin
from django import forms
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import ReadOnlyPasswordHashField
from django.utils.translation import ugettext_lazy as _

from evap.evaluation.models import Contribution, Course, RatingAnswerCounter, Question, Questionnaire, Semester, TextAnswer, UserProfile


class ContributionInline(admin.TabularInline):
    model = Contribution
    extra = 3


class CourseAdmin(admin.ModelAdmin):
    model = Course
    inlines = [ContributionInline]
    list_display = ('__str__', 'semester', 'type')
    list_filter = ('semester',)
    readonly_fields = ('state',)
    if not settings.DEBUG:
        readonly_fields += ('voters',)


class QuestionInline(admin.TabularInline):
    model = Question
    extra = 3


class QuestionnaireAdmin(admin.ModelAdmin):
    model = Questionnaire
    inlines = [QuestionInline]
    list_filter = ('obsolete',)


class UserCreationForm(forms.ModelForm):
    """A form for creating new users. Includes all the required fields, plus a repeated password."""
    password1 = forms.CharField(label=_('Password'), widget=forms.PasswordInput)
    password2 = forms.CharField(label=_('Password confirmation'), widget=forms.PasswordInput)

    class Meta:
        model = UserProfile
        fields = ('username', 'email', 'first_name', 'last_name')

    def clean_password2(self):
        # Check that the two password entries match
        password1 = self.cleaned_data.get("password1")
        password2 = self.cleaned_data.get("password2")
        if password1 and password2 and password1 != password2:
            raise forms.ValidationError(_("Passwords don't match"))
        return password2

    def save(self, commit=True):
        # Save the provided password in hashed format
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password1"])
        if commit:
            user.save()
        return user


class UserChangeForm(forms.ModelForm):
    """A form for updating users. Includes all the fields on the user, but replaces the password field with admin's password hash display field."""
    password = ReadOnlyPasswordHashField()

    class Meta:
        model = UserProfile
        fields = ('username', 'password', 'email', 'first_name', 'last_name')

    def clean_password(self):
        # Regardless of what the user provides, return the initial value.
        # This is done here, rather than on the field, because the
        # field does not have access to the initial value
        return self.initial["password"]


class UserProfileAdmin(UserAdmin):
    # The forms to add and change user instances
    form = UserChangeForm
    add_form = UserCreationForm

    # The fields to be used in displaying the User model.
    # These override the definitions on the base UserAdmin
    # that reference specific fields on auth.User.
    list_display = ('username', 'email', 'first_name', 'last_name', 'is_superuser')
    list_filter = ()
    fieldsets = (
        (None, {'fields': ('username', 'email', 'password', 'login_key', 'login_key_valid_until')}),
        ('Personal info', {'fields': ('first_name', 'last_name', 'title')}),
        ('Delegates and cc-users', {'fields': ('delegates', 'cc_users')}),
        ('Permissions', {'fields': ('is_superuser', 'groups', 'user_permissions',)}),
    )
    # add_fieldsets is not a standard ModelAdmin attribute. UserAdmin
    # overrides get_fieldsets to use this attribute when creating a user.
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'email', 'first_name', 'last_name', 'password1', 'password2')
        }),
    )
    search_fields = ('username',)
    ordering = ('username',)
    filter_horizontal = []


admin.site.register(Semester)
admin.site.register(Course, CourseAdmin)

admin.site.register(Questionnaire, QuestionnaireAdmin)

admin.site.register(UserProfile, UserProfileAdmin)

if settings.DEBUG:
    admin.site.register(TextAnswer)
    admin.site.register(RatingAnswerCounter)
