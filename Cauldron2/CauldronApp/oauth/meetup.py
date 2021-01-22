from urllib.parse import urlencode

import requests
from django.conf import settings
from django.http import HttpResponseRedirect
from django.urls import reverse

from CauldronApp.oauth import oauth


class MeetupOAuth(oauth.OAuth):
    AUTH_URL = 'https://secure.meetup.com/oauth2/authorize'
    ACCESS_TOKEN_URL = 'https://secure.meetup.com/oauth2/access'
    REDIRECT_PATH = '/meetup-login'

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
            return f"Meetup API Error. {r.status_code}: {r.reason}"
        response = r.json()
        self.token = response.get('access_token', None)
        self.refresh_token = response.get('refresh_token', None)
        if not self.token:
            return f"GitLab API Error. Oauth token not found for the authorization"

    def user_data(self):
        r = requests.get('https://api.meetup.com/members/self?&sign=true&photo-host=public',
                         headers={'Authorization': 'bearer {}'.format(self.token)})
        data_user = r.json()
        try:
            photo = data_user['photo']['photo_link']
        except KeyError:
            photo = '/static/img/profile-default.png'

        return oauth.OAuthUser(username=data_user['id'],
                               name=data_user['name'],
                               photo=photo,
                               token=self.token,
                               refresh_token=self.refresh_token)


def start_oauth(request):
    """Start the Oauth authentication for this backend"""
    redirect_uri = request.build_absolute_uri(reverse('meetup_callback'))
    params = urlencode({'client_id': settings.MEETUP_CLIENT_ID,
                        'response_type': 'code',
                        'redirect_uri': redirect_uri})
    return HttpResponseRedirect(f"{MeetupOAuth.AUTH_URL}?{params}")
