from django.conf import settings
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import resolve, reverse

from CauldronApp.views import create_context
from cauldron_apps.cauldron.models import Project


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


class LoginRequiredMiddleware:
    """
    Middleware that checks if the user is authenticated before using Cauldron.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            return self.get_response(request)

        resolver = resolve(request.path)
        if resolver.view_name in settings.LOGIN_REQUIRED_IGNORE_VIEW_NAMES:
            return self.get_response(request)
        elif resolver.route.startswith('project/'):
            try:
                if Project.objects.get(id=resolver.kwargs['project_id']).public:
                    return self.get_response(request)
            except (KeyError, Project.DoesNotExist):
                pass
        return HttpResponseRedirect(reverse('login_page'))
