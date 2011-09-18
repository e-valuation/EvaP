from evaluation.models import Semester


def all_semesters():
    semesters = Semester.objects.filter(visible=True)
    return {'semesters': semesters}
