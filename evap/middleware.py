from django.contrib.auth.views import redirect_to_login


class RequireLoginMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    @staticmethod
    def process_view(request, view_func, _view_args, _view_kwargs):
        # Returning None tells django to pass the request on
        if request.user.is_authenticated:
            return None

        if "no_login_required" in view_func.__dict__ and view_func.no_login_required:
            return None

        return redirect_to_login(request.get_full_path())


def no_login_required(func):
    func.no_login_required = True
    return func
