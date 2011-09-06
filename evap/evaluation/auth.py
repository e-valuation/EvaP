from django.contrib.auth.decorators import user_passes_test

def fsr_required(func):
    """
    Decorator for views that checks that the user is logged in, redirecting
    to the log-in page if necessary.
    """
    
    def check_user(user):
        if not user.is_authenticated():
            return False
        return user.get_profile().fsr
    
    dec = user_passes_test(check_user)
    if func:
        return dec(func)
    return dec

def lecturer_required(func):
    """
    Decorator for views that checks that the user is logged in, redirecting
    to the log-in page if necessary.
    """
    
    def check_user(user):
        if not user.is_authenticated():
            return False
        return user.get_profile().lectures_courses()
    
    dec = user_passes_test(check_user)
    if func:
        return dec(func)
    return dec