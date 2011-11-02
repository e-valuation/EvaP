from django.shortcuts import redirect

def index(request):
    return redirect('evap.student.views.index')
