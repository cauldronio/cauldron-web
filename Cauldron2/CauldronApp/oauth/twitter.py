from requests_oauthlib import OAuth1Session
from django.conf import settings
from django.http import HttpResponseRedirect
from django.urls import reverse

from CauldronApp.oauth import oauth


class TwitterOAuth(oauth.OAuth):
    REQUEST_TOKEN_URL = 'https://api.twitter.com/oauth/request_token'
    AUTH_URL = 'https://api.twitter.com/oauth/authenticate'
    ACCESS_TOKEN_URL = 'https://api.twitter.com/oauth/access_token'

    def __init__(self, client_id, client_secret, redirect_uri):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.token = None
        self.refresh_token = None

    def authenticate(self, oauth_token, verifier):
        oauth_session = OAuth1Session(self.client_id,
                                      client_secret=self.client_secret,
                                      resource_owner_key=oauth_token,
                                      verifier=verifier)

        oauth_tokens = oauth_session.fetch_access_token(self.ACCESS_TOKEN_URL)

        self.resource_owner_key = oauth_tokens.get('oauth_token')
        self.resource_owner_secret = oauth_tokens.get('oauth_token_secret')

    def user_data(self):
        protected_url = 'https://api.twitter.com/1.1/account/verify_credentials.json'
        oauth_session = OAuth1Session(self.client_id,
                                      client_secret=self.client_secret,
                                      resource_owner_key=self.resource_owner_key,
                                      resource_owner_secret=self.resource_owner_secret)
        r = oauth_session.get(protected_url)

        if not r.ok:
            return None

        response = r.json()
        try:
            photo = response['profile_image_url_https']
        except KeyError:
            photo = '/static/img/profile-default.png'

        return oauth.OAuthUser(username=response['screen_name'],
                               name=response['screen_name'],
                               photo=photo,
                               token=None,
                               refresh_token=None)


def start_oauth(request):
    """Start the Oauth authentication for this backend"""
    # Store data passed in QueryDict
    request.session['store_oauth'] = request.GET.dict()
    redirect_uri = request.build_absolute_uri(reverse('twitter_callback'))

    oauth_session = OAuth1Session(settings.TWITTER_CLIENT_ID,
                                  client_secret=settings.TWITTER_CLIENT_SECRET,
                                  callback_uri=redirect_uri)
    oauth_session.fetch_request_token(TwitterOAuth.REQUEST_TOKEN_URL)

    authorization_url = oauth_session.authorization_url(TwitterOAuth.AUTH_URL)
    return HttpResponseRedirect(authorization_url)
