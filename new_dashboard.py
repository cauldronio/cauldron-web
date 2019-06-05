import requests
from archimedes.archimedes import Archimedes
import logging
logging.basicConfig(level=logging.INFO)


ES_URL = "https://localhost:9200"
KIB_URL = "http://localhost:5601"

USER_NAME = "dashboard-2-user"
USER_PSW = "ChangemePlse"

ADMIN_NAME = 'admin'
ADMIN_PSW = 'ChangemePlse'

ROLE_NAME = "dashboard-2-role"

PANELS_DIR = "overview"

INDICES = ["chaoss_grimoirelab-perceval", "chaoss-grimoirelab-perceval", "github_chaoss_augur", "git-chaoss-augur"]


# ADD USER
logging.info('ADDING USER')
headers = {'Content-Type': 'application/json'}
r = requests.put("{}/_opendistro/_security/api/internalusers/{}".format(ES_URL, USER_NAME),
                 auth=(ADMIN_NAME, ADMIN_PSW),
                 json={"password": USER_PSW},
                 verify=False,
                 headers=headers)

logging.info(r.status_code, r.text)

r.raise_for_status()


# CREATE THE ROLE
logging.info('ADDING ROLE')

role = {
        "indices": {
            # Here comes each index
        }
    }
for index in INDICES:
    role['indices']["*{}".format(index)] = {"*": ["READ"]}

headers = {'Content-Type': 'application/json'}
r = requests.put("{}/_opendistro/_security/api/roles/{}".format(ES_URL, ROLE_NAME),
                 auth=(ADMIN_NAME, ADMIN_PSW),
                 json=role,
                 verify=False,
                 headers=headers)
logging.info(r.status_code, r.text)

r.raise_for_status()

# CREATE ROLE MAPPING
logging.info("Creating Role Mapping")

headers = {'Content-Type': 'application/json'}
r = requests.put("{}/_opendistro/_security/api/rolesmapping/{}".format(ES_URL, ROLE_NAME),
                 auth=(ADMIN_NAME, ADMIN_PSW),
                 json={"users": [USER_NAME]},
                 verify=False,
                 headers=headers)

logging.info(r.status_code, r.text)

r.raise_for_status()

# Include Overview
archimedes = Archimedes("http://{}:{}@localhost:5601".format(USER_NAME, USER_PSW), PANELS_DIR)
archimedes.import_from_disk(obj_type='dashboard', obj_id='Overview',
                            find=True, force=False)


# Set default Index pattern
logging.info('Set default index pattern')
headers = {'Content-Type': 'application/json', 'kbn-xsrf': 'true'}
requests.post('{}/api/kibana/settings/defaultIndex'.format(ES_URL),
              auth=(USER_NAME, USER_PSW),
              json={"value": "git_enrich"},
              verify=False,
              headers=headers)


logging.info(r.status_code, r.text)

r.raise_for_status()


