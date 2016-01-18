from evap.grades.models import SemesterGradeDownloadActivation


def are_grades_activated(semester):
    try:
        activation = SemesterGradeDownloadActivation.objects.get(semester=semester)
        return activation.is_active
    except SemesterGradeDownloadActivation.DoesNotExist:
        return False
