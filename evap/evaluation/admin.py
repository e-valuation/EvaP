from evaluation.models import Course, Question, QuestionGroup, Semester
from django.contrib import admin


class CourseAdmin(admin.ModelAdmin):
    model = Course
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
