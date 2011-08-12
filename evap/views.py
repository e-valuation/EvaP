from django.shortcuts import redirect

def index(request):
    return redirect('evaluation.views.student_index')
