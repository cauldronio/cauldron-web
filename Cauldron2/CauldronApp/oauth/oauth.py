import collections

OAuthUser = collections.namedtuple('OauthUser', 'username, name, photo, token, refresh_token')


class OAuth:
    """
    Oauth base class
    """
    def authenticate(self, code):
        raise NotImplementedError

    def user_data(self):
        raise NotImplementedError
