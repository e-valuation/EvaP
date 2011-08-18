from django.contrib.auth.models import User
from evaluation.models import Course

def find_or_create_user(username, **otherProperties):
    try:
        return User.objects.get(username=username)
    except User.DoesNotExist:
        user = User(username=username, **otherProperties)
        user.save()
        return user

def find_or_create_course(semester, name_de, **otherProperties):
    try:
        return semester.course_set.get(name_de=name_de)
    except Course.DoesNotExist:
        course = Course(semester=semester, name_de=name_de, **otherProperties)
        course.save()
        return course
    
