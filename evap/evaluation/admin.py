from evaluation.models import Course, Semester, QuestionGroup, Question
from django.contrib import admin

class QuestionInline(admin.StackedInline):
    model = Question
    extra = 3


class QuestionGroupAdmin(admin.ModelAdmin):
    inlines = [QuestionInline]


admin.site.register(Course)
admin.site.register(Semester)
admin.site.register(QuestionGroup, QuestionGroupAdmin)
