from evap.evaluation.models import Semester, Questionnaire

def all_semesters():
    semesters = Semester.objects.all()
    return {'semesters': semesters}

def all_questionnaires():
    questionnaires = Questionnaire.objects.filter(obsolete=False)
    return {'questionnaires': questionnaires}
