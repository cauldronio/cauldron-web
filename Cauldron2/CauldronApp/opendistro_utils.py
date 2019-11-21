import logging
import requests

logger = logging.getLogger(__name__)


class OpendistroApi:
    """
    Functions for calling OpenDistro API from Cauldron
    """
    def __init__(self, es_url, admin_password):
        self.es_url = es_url
        self.admin_password = admin_password

    def create_user(self, username, password):
        """
        Create a new OpenDistro user with the defined parameters
        :param username: name for the user
        :param password: password for the user
        :return:
        """
        headers = {'Content-Type': 'application/json'}

        data = {"password": password}

        logger.info('Creating ODFE user: <{}>'.format(username))
        r = requests.put("{}/_opendistro/_security/api/internalusers/{}".format(self.es_url, username),
                         auth=('admin', self.admin_password),
                         json=data,
                         verify=False,
                         headers=headers)
        logger.info("Result creating user: {} - {}".format(r.status_code, r.text))
        return r.ok

    def put_role(self, name, permissions=None):
        """
        Creates or replaces the specified role and apply/remove permissions
        Docs: https://opendistro.github.io/for-elasticsearch-docs/docs/security-access-control/api/#create-role
        :param name: name for the role
        :param permissions: permissions for the role. If not permissions defined, it will
                            only have read permissions over a index named 'none'
        :return:
        """
        if not permissions:
            permissions = {
                "index_permissions": [{
                    "index_patterns": [
                        "none"
                    ],
                    "allowed_actions": [
                        "read"
                    ]
                }]
            }
        headers = {'Content-Type': 'application/json'}

        logger.info('Put ODFE role: <{}> with permissions'.format(name, permissions))
        r = requests.put("{}/_opendistro/_security/api/roles/{}".format(self.es_url, name),
                         auth=('admin', self.admin_password),
                         json=permissions,
                         verify=False,
                         headers=headers)
        logger.info("{} - {}".format(r.status_code, r.text))
        return r.ok

    def create_mapping(self, users, role_name):
        """
        Create a role mapping in OpenDistro
        :param users: A list of users that are added to the rolemapping
        :param role_name: Name for the role to be included
        :return:
        """

        headers = {'Content-Type': 'application/json'}

        data = {"users": users}

        logger.info('Creating ES role mapping between: <{}> and <{}>'.format(users, role_name))
        r = requests.put("{}/_opendistro/_security/api/rolesmapping/{}".format(self.es_url, role_name),
                         auth=('admin', self.admin_password),
                         json=data,
                         verify=False,
                         headers=headers)
        logging.info("{} - {}".format(r.status_code, r.text))
        return r.ok
