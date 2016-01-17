from evap.grades.models import SemesterGradeActivation


def are_grades_activated(semester):
    try:
        activation = SemesterGradeActivation.objects.get(semester=semester)
        return activation.is_active
    except SemesterGradeActivation.DoesNotExist:
        return False
