import requests
from django.conf import settings
from django.http import HttpResponseRedirect
from django.urls import reverse
from github import Github
from urllib.parse import urlencode

from CauldronApp.oauth import oauth


class GitHubOAuth(oauth.OAuth):
    AUTH_URL = 'https://github.com/login/oauth/authorize'
    ACCESS_TOKEN_URL = 'https://github.com/login/oauth/access_token'

    def __init__(self, client_id, client_secret):
        self.client_id = client_id
        self.client_secret = client_secret
        self.token = None
        self.refresh_token = None

    def authenticate(self, code):
        headers = {
            'Accept': 'application/json'
        }
        data = {
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'code': code
        }
        r = requests.post(self.ACCESS_TOKEN_URL,
                          data=data,
                          headers=headers)
        if not r.ok:
            return f"GitHub API Error. {r.status_code}: {r.reason}"
        self.token = r.json().get('access_token', None)
        if not self.token:
            return f"GitHub API Error. Oauth token not found for the authorization"

    def user_data(self):
        gh = Github(self.token)
        user = gh.get_user()
        return oauth.OAuthUser(username=user.login,
                               name=user.login,
                               photo=user.avatar_url,
                               token=self.token,
                               refresh_token=self.refresh_token)


def start_oauth(request):
    """Start the Oauth authentication for this backend"""
    redirect_uri = request.build_absolute_uri(reverse('github_callback'))
    params = urlencode({'client_id': settings.GH_CLIENT_ID,
                        'response_type': 'code',
                        'redirect_uri': redirect_uri})
    return HttpResponseRedirect(f"{GitHubOAuth.AUTH_URL}?{params}")
