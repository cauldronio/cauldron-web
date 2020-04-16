import requests
import logging
import tempfile

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.WARNING)


def import_object(kibana_url, admin_password, obj, tenant):
    """
    This method import the object passed as argument in Kibana using saved_objects API
    :return:
    """
    logger.debug(f'Importing object')

    headers = {'kbn-xsrf': 'true',
               'securitytenant': tenant}
    saved_objects_api = f"{kibana_url}/api/saved_objects/_import?overwrite=true"
    f = tempfile.NamedTemporaryFile(suffix='.ndjson')
    f.write(obj)
    f.seek(0)
    files = {'file': f}
    r = requests.post(saved_objects_api,
                      auth=('admin', admin_password),
                      verify=False,
                      files=files,
                      headers=headers)
    f.close()
    logger.debug(f'{r.status_code} - {r.json()}')


def export_all_objects(kibana_url, admin_password, tenant):
    """
    This method export all the object from the defined tenant using saved_objects API and returns the contents
    :return:
    """
    logger.debug(f'Exporting all from {tenant}')

    headers = {'kbn-xsrf': 'true',
               'securitytenant': tenant}
    data = {
        "type": ["index-pattern", "visualization", "dashboard", "search", "config", "query", "url"],
        "includeReferencesDeep": True
    }
    saved_objects_api = f"{kibana_url}/api/saved_objects/_export"

    r = requests.post(saved_objects_api,
                      auth=('admin', admin_password),
                      data=data,
                      verify=False,
                      headers=headers)
    logger.debug(f'{r.status_code}')

    return r.content
