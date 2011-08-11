from evaluation.models import Course, Question, Questionnaire, QuestionGroup, Semester
from django.contrib import admin


class QuestionnaireInline(admin.TabularInline):
    model = Questionnaire
    extra = 3


class CourseAdmin(admin.ModelAdmin):
    model = Course
    inlines = [QuestionnaireInline]
    list_display = ('__unicode__', 'semester')
    list_filter = ('semester',)


class QuestionInline(admin.TabularInline):
    model = Question
    extra = 3


class QuestionGroupAdmin(admin.ModelAdmin):
    model = QuestionGroup
    inlines = [QuestionInline]


admin.site.register(Course, CourseAdmin)
admin.site.register(QuestionGroup, QuestionGroupAdmin)
admin.site.register(Semester)
