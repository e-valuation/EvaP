from django.contrib.auth.models import User
from evaluation.models import Course

def find_student(data):
    try:
        return User.objects.get(username=data[3])
    except User.DoesNotExist:
        user = User(username = data[3], first_name = data[1], last_name = data[2])
        user.save()
        return user

def find_course(semester, data):
    try:
        return semester.course_set.get(name_de=data[5])
    except Course.DoesNotExist:
        course = Course(name_de = data[5], name_en = data[6], semester = semester)
        course.save()
        return course