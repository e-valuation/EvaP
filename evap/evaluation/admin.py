from evap.evaluation.models import Contribution, Course, LikertAnswer, Question, \
                                   Questionnaire, Semester, TextAnswer, UserProfile
from django.conf import settings
from django.contrib import admin


class ContributionInline(admin.TabularInline):
    model = Contribution
    extra = 3


class CourseAdmin(admin.ModelAdmin):
    model = Course
    inlines = [ContributionInline]
    list_display = ('__unicode__', 'semester', 'kind')
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


class UserProfileAdmin(admin.ModelAdmin):
    model = UserProfile
    list_display = ('full_name', 'user')
    ordering = ('user__username',)


admin.site.register(Semester)
admin.site.register(Course, CourseAdmin)

admin.site.register(Questionnaire, QuestionnaireAdmin)

admin.site.register(UserProfile, UserProfileAdmin)

if settings.DEBUG:
    admin.site.register(TextAnswer)
    admin.site.register(LikertAnswer)
