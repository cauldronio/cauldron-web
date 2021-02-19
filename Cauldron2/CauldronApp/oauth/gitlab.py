import requests
from urllib.parse import urljoin, urlencode

from django.urls import reverse
from gitlab import Gitlab
from django.http import HttpResponseRedirect, HttpResponse

from CauldronApp.oauth import oauth
from cauldron_apps.poolsched_gitlab.models import GLInstance


class GitLabOAuth(oauth.OAuth):
    AUTH_PATH = '/oauth/authorize'
    TOKEN_PATH = '/oauth/token'

    def __init__(self, instance, callback_uri):
        self.callback_uri = callback_uri
        self.token = None
        self.refresh_token = None
        self.instance = instance

    def authenticate(self, code):
        headers = {
            'Accept': 'application/json'
        }
        params = {
            'client_id': self.instance.client_id,
            'client_secret': self.instance.client_secret,
            'code': code,
            'grant_type': 'authorization_code',
            'redirect_uri': self.callback_uri
        }
        r = requests.post(urljoin(self.instance.endpoint, self.TOKEN_PATH),
                          params=params,
                          headers=headers)
        if not r.ok:
            return f"GitLab API Error. {r.status_code}: {r.reason}"
        self.token = r.json().get('access_token', None)
        if not self.token:
            return f"GitLab API Error. Oauth token not found for the authorization"

    def user_data(self):
        gl = Gitlab(url=self.instance.endpoint, oauth_token=self.token)
        gl.auth()
        return oauth.OAuthUser(username=gl.user.attributes['username'],
                               name=gl.user.attributes['username'],
                               photo=gl.user.attributes['avatar_url'],
                               token=self.token,
                               refresh_token=self.refresh_token)


def start_oauth(request, backend):
    """Start the Oauth authentication for this backend"""
    # Store data passed in QueryDict
    request.session['store_oauth'] = request.GET.dict()
    try:
        instance = GLInstance.objects.get(slug=backend)
    except GLInstance.DoesNotExist:
        return HttpResponse(f'Backend {backend} not found.', status=404)
    redirect_uri = request.build_absolute_uri(reverse('gitlab_callback', kwargs={'backend': backend}))
    params = urlencode({'client_id': instance.client_id,
                        'response_type': 'code',
                        'redirect_uri': redirect_uri})
    oauth_url = urljoin(instance.endpoint, GitLabOAuth.AUTH_PATH)
    return HttpResponseRedirect(f"{oauth_url}?{params}")
