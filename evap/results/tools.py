from evap.evaluation.models import Semester


def all_semesters():
    semesters = Semester.get_all_with_published_courses()
    return {'semesters': semesters}
