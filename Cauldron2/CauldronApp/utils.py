import os
from functools import wraps

import jwt
from django.http import JsonResponse
from django.urls import reverse


def get_jwt_key(user, backend_roles):
    """
    Return the JWT key for a specific user and role
    :param user:
    :param backend_roles: String or list of backend roles
    :return:
    """
    dirname = os.path.dirname(os.path.abspath(__file__))
    key_location = os.path.join(dirname, 'jwtR256.key')
    with open(key_location, 'r') as f_private:
        private_key = f_private.read()
    claims = {
        "user": user,
        "roles": backend_roles
    }
    return jwt.encode(claims, private_key, algorithm='RS256').decode('utf-8')


def require_authenticated(json_response=True):
    """
    Decorator to check a user is authenticated.  Usage::

        @authorized_user()
        def my_view(request):
    """
    def decorator(func):
        @wraps(func)
        def inner(request, *args, **kwargs):
            if not request.user.is_authenticated:
                if json_response:
                    return JsonResponse({'status': 'error', 'message': 'You are not authenticated'}, status=401)
            return func(request, *args, **kwargs)
        return inner
    return decorator