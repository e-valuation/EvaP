from evaluation.models import Semester, QuestionGroup

def all_semesters():
    semesters = Semester.objects.all()
    return {'semesters': semesters}

def all_questiongroups():
    questiongroups = QuestionGroup.objects.filter(obsolete=False)
    return {'questiongroups': questiongroups}
