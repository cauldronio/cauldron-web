import logging
import requests

logger = logging.getLogger(__name__)
# logging.basicConfig(level=logging.DEBUG)


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

    def create_role(self, name, permissions=None):
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

    def delete_role(self, name):
        """
        Delete a OpenDistro role
        :param name: name of the role
        :return:
        """
        headers = {'Content-Type': 'application/json'}

        logger.info('Delete ODFE role: <{}>'.format(name))
        r = requests.delete("{}/_opendistro/_security/api/roles/{}".format(self.es_url, name),
                            auth=('admin', self.admin_password),
                            verify=False,
                            headers=headers)
        logger.info("Result deleting roles: {} - {}".format(r.status_code, r.text))
        return r.ok

    def create_mapping(self, role, backend_roles=None, hosts=None, users=None):
        """
        Include the users, hosts and backend_roles that are linked with the desired role
        :return:
        """
        headers = {'Content-Type': 'application/json'}
        data = dict()
        data['backend_roles'] = backend_roles if backend_roles else []
        data['hosts'] = hosts if hosts else []
        data['users'] = users if users else []

        logger.info('Creating ES role mapping between: <{}> and <{}>'.format(data, role))
        r = requests.put("{}/_opendistro/_security/api/rolesmapping/{}".format(self.es_url, role),
                         auth=('admin', self.admin_password),
                         json=data,
                         verify=False,
                         headers=headers)
        logger.info("{} - {}".format(r.status_code, r.text))
        return r.ok

    def delete_mapping(self, role_name):
        """
        Delete a OpenDistro role mapping
        :param role_name: name of the role
        :return:
        """
        headers = {'Content-Type': 'application/json'}

        logger.info('Delete ODFE role mapping: <{}>'.format(role_name))
        r = requests.delete("{}/_opendistro/_security/api/rolesmapping/{}".format(self.es_url, role_name),
                            auth=('admin', self.admin_password),
                            verify=False,
                            headers=headers)
        logger.info("Result deleting role mapping: {} - {}".format(r.status_code, r.text))
        return r.ok

    def delete_user(self, username):
        """
        Delete a OpenDistro user
        :param username: name of the user
        :return:
        """
        headers = {'Content-Type': 'application/json'}

        logger.info('Delete ODFE user: <{}>'.format(username))
        r = requests.delete("{}/_opendistro/_security/api/internalusers/{}".format(self.es_url, username),
                            auth=('admin', self.admin_password),
                            verify=False,
                            headers=headers)
        logger.info("Result deleting user: {} - {}".format(r.status_code, r.text))
        return r.ok

    def create_tenant(self, name):
        """
        Creates a new tenant for the user
        :param name:
        :return:
        """
        headers = {'Content-Type': 'application/json'}

        data = {"description": "Workspace of the user"}

        logger.info('Creating ODFE tenant: <{}>'.format(name))
        r = requests.put("{}/_opendistro/_security/api/tenants/{}".format(self.es_url, name),
                         auth=('admin', self.admin_password),
                         json=data,
                         verify=False,
                         headers=headers)
        logger.info("Result creating user: {} - {}".format(r.status_code, r.text))
        return r.ok

    def delete_tenant(self, name):
        """
        Deletes a specific tenant
        :param name:
        :return:
        """
        headers = {'Content-Type': 'application/json'}

        logger.info('Delete ODFE tenant: <{}>'.format(name))
        r = requests.delete("{}/_opendistro/_security/api/tenants/{}".format(self.es_url, name),
                            auth=('admin', self.admin_password),
                            verify=False,
                            headers=headers)
        logger.info("Result deleting tenant: {} - {}".format(r.status_code, r.text))
        return r.ok
