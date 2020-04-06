import requests
from gitlab import Gitlab

from CauldronApp.oauth import oauth


class GitLabOAuth(oauth.OAuth):
    AUTH_URL = 'https://gitlab.com/oauth/authorize'
    ACCESS_TOKEN_URL = 'https://gitlab.com/oauth/token'
    REDIRECT_PATH = '/gitlab-login'

    def __init__(self, client_id, client_secret, redirect_uri):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.token = None
        self.refresh_token = None

    def authenticate(self, code):
        headers = {
            'Accept': 'application/json'
        }
        params = {
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'code': code,
            'grant_type': 'authorization_code',
            'redirect_uri': self.redirect_uri
        }
        r = requests.post(self.ACCESS_TOKEN_URL,
                          params=params,
                          headers=headers)
        if not r.ok:
            return f"GitLab API Error. {r.status_code}: {r.reason}"
        self.token = r.json().get('access_token', None)
        if not self.token:
            return f"GitLab API Error. Oauth token not found for the authorization"

    def user_data(self):
        gl = Gitlab(url='https://gitlab.com', oauth_token=self.token)
        gl.auth()
        return oauth.OAuthUser(username=gl.user.attributes['username'],
                               name=gl.user.attributes['username'],
                               photo=gl.user.attributes['avatar_url'],
                               token=self.token,
                               refresh_token=self.refresh_token)



