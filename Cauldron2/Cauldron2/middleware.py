from django.shortcuts import render
from CauldronApp.views import create_context


class HatstallAuthorizationMiddleware:
    """
    Middleware that handles Hatstall authentication permissions.

    By default, it checks if the user is admin for accessing Hatstall.
    If it is not, the user receives an error message informing that
    is not allowed.
    """
    def __init__(self, get_response):
        self.get_response = get_response
        self.hatstall_url = "/hatstall"

    def __call__(self, request):
        if request.path.startswith(self.hatstall_url):
            if request.user and request.user.is_superuser:
                response = self.get_response(request)
                return response
            else:
                context = create_context(request)
                context['title'] = "Not authorized"
                context['description'] = "You need to login as admin user"
                return render(request, 'cauldronapp/error.html', status=401, context=context)

        response = self.get_response(request)
        return response


