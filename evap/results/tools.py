from evap.evaluation.models import Semester


def all_semesters():
    semesters = Semester.objects.all()
    return {'semesters': semesters}
