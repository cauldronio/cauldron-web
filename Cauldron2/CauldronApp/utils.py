import os
import jwt


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
