import re
import requests

from CauldronApp.models import MeetupRepository
from poolsched import api as sched_api


def parse_input_data(data):
    """Return the group name for the data provided"""
    meetup_group_regex = '([a-zA-Z0-9\-]{6,70})'
    language_code = '(?:\/[a-zA-Z0-9\-]{2,5})?'
    data = data.strip()

    re_url_group = re.match(f'^https?:\/\/www\.meetup\.com{language_code}\/{meetup_group_regex}\/?', data)
    if re_url_group:
        return re_url_group.groups()[0]
    re_group = re.match(f'^{meetup_group_regex}$', data)
    if re_group:
        return re_group.groups()[0]

    return None


def analyze_meetup(project, group):
    """IMPORTANT: update the repo role after this call"""
    repo, created = MeetupRepository.objects.get_or_create(group=group)
    if created:
        repo.link_sched_repo()
    repo.projects.add(project)
    sched_api.analyze_meetup_repo_obj(project.creator, repo.repo_sched)


def analyze_data(project, data):
    """IMPORTANT: update the repo role after this call"""
    group = parse_input_data(data)
    if group:
        r = requests.get('https://api.meetup.com/{}'.format(group),
                         headers={'Authorization': 'bearer {}'.format(project.creator.meetuptokens.first().token)})
        group_info = r.json()
        if 'errors' in group_info:
            error_msg = group_info['errors'][0]['message']
            return {'status': 'error',
                    'message': f'Error from Meetup API. {error_msg}',
                    'code': 500}
        analyze_meetup(project, group)

        return {'status': 'ok', 'code': 200}

    return {'status': 'error',
            'message': 'Is that a valid URL or group?',
            'code': 400}
