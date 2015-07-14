from django.contrib import admin
from evap.grades.models import GradeDocument

class GradeDocumentAdmin(admin.ModelAdmin):
    model = GradeDocument
    list_display = ('__unicode__', 'course', 'type')
    list_filter = ('type',)


admin.site.register(GradeDocument, GradeDocumentAdmin)
