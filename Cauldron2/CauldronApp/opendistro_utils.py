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
        Create a new OpenDistro user with the defined user and password
        :param username: Name for the OpenDistro user
        :param password: Password for the user
        :return:
        """
        headers = {'Content-Type': 'application/json'}

        logger.info('Creating ODFE user: <{}>'.format(username))
        r = requests.put("{}/_opendistro/_security/api/internalusers/{}".format(self.es_url, username),
                         auth=('admin', self.admin_password),
                         json={"password": password},
                         verify=False,
                         headers=headers)
        logger.info("Result creating user: {} - {}".format(r.status_code, r.text))
        return r.ok

    def create_role(self, name, tenant_name=None):
        """
        Create a new OpenDistro role
        :param name: name for the role
        :param tenant_name: name for the tenant to be included in the role
        :return:
        """
        data = {"indices":
                {'none': {"*": ["READ"]}},
                }
        if tenant_name:
            data["tenants"]: {tenant_name: 'RW'}
        headers = {'Content-Type': 'application/json'}

        logger.info('Creating ODFE role: <{}>'.format(name))
        r = requests.put("{}/_opendistro/_security/api/roles/{}".format(self.es_url, name),
                         auth=('admin', self.admin_password),
                         json=data,
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

        logger.info('Creating ES role mapping between: <{}> and <{}>'.format(users, role_name))
        r = requests.put("{}/_opendistro/_security/api/rolesmapping/{}".format(self.es_url, role_name),
                         auth=('admin', self.admin_password),
                         json={"users": users},
                         verify=False,
                         headers=headers)
        logging.info("{} - {}".format(r.status_code, r.text))
        return r.ok
