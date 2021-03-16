import requests
from django.conf import settings
from django.http import HttpResponseRedirect
from django.urls import reverse
from urllib.parse import urlencode, parse_qs

from CauldronApp.oauth import oauth


class StackExchangeOAuth(oauth.OAuth):
    AUTH_URL = 'https://stackoverflow.com/oauth'
    ACCESS_TOKEN_URL = 'https://stackoverflow.com/oauth/access_token'

    def __init__(self, client_id, client_secret, app_key, redirect_uri):
        self.client_id = client_id
        self.client_secret = client_secret
        self.token = None
        self.redirect_uri = redirect_uri
        self.app_key = app_key

    def authenticate(self, code):
        headers = {
            'Accept': 'application/x-www-form-urlencoded'
        }
        data = {
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'code': code,
            'redirect_uri': self.redirect_uri
        }
        r = requests.post(self.ACCESS_TOKEN_URL,
                          data=data,
                          headers=headers)
        if not r.ok:
            return f"StackExchange API Error. {r.status_code}: {r.reason}"
        self.token = r
        token_qs = parse_qs(r.content.decode()).get('access_token', None)
        if token_qs:
            self.token = token_qs[0]
        if not self.token:
            return f"GitHub API Error. Oauth token not found for the authorization"

    def user_data(self):
        data = {
            'site': 'stackoverflow',
            'access_token': self.token,
            'key': self.app_key
        }
        r = requests.get("https://api.stackexchange.com/2.2/me",
                         data=data)
        users = r.json()

        try:
            me = users['items'][0]
            return oauth.OAuthUser(username=me['user_id'],
                                   name=me['display_name'],
                                   photo=me['profile_image'],
                                   token=self.token,
                                   refresh_token=None)
        except (IndexError, KeyError):
            return None


def start_oauth(request):
    """Start the Oauth authentication for this backend"""
    # Store data passed in QueryDict
    request.session['store_oauth'] = request.GET.dict()
    redirect_uri = request.build_absolute_uri(reverse('stackexchange_callback'))
    params = urlencode({'client_id': settings.STACK_EXCHANGE_CLIENT_ID,
                        'scope': 'no_expiry',
                        'redirect_uri': redirect_uri})
    return HttpResponseRedirect(f"{StackExchangeOAuth.AUTH_URL}?{params}")
