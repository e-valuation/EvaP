from evap.evaluation.models import Semester


def all_semesters():
    semesters = Semester.objects.filter(course__state="published")
    return {'semesters': semesters}
