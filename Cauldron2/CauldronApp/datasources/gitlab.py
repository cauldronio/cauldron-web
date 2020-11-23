import re
import time
import requests
import logging

from CauldronApp.models import GitLabRepository
from CauldronApp.datasources import git
from cauldron_apps.poolsched_gitlab.api import analyze_gl_repo_obj


def parse_input_data(data):
    """Return a tuple (owner, repository). Return None in owner or repository in the case was not found"""
    gl_user_regex = '([a-zA-Z0-9_\.][a-zA-Z0-9_\-\.]{1,200}[a-zA-Z0-9_\-]|[a-zA-Z0-9_])'
    gl_repo_regex = '((?:[a-zA-Z0-9_\.][a-zA-Z0-9_\-\.]*(?:\/)?)+)'
    data = data.strip()

    re_user = re.match('^{}$'.format(gl_user_regex), data)
    if re_user:
        return re_user.groups()[0], None
    re_url_user = re.match(f'^https?:\/\/gitlab\.com\/{gl_user_regex}\/?$', data)
    if re_url_user:
        return re_url_user.groups()[0], None
    re_url_repo = re.match(f'^https?:\/\/gitlab\.com\/{gl_user_regex}\/{gl_repo_regex}(?:.git)?$', data)
    if re_url_repo:
        return re_url_repo.groups()[0], re_url_repo.groups()[1]
    re_user_repo = re.match(f'{gl_user_regex}/{gl_repo_regex}$', data)
    if re_user_repo:
        return re_user_repo.groups()[0], re_user_repo.groups()[1]

    return None, None


def analyze_gitlab(project, owner, repo):
    """IMPORTANT: update the repo role after this call"""
    repo, created = GitLabRepository.objects.get_or_create(owner=owner, repo=repo)
    if created:
        repo.link_sched_repo()
    repo.projects.add(project)
    analyze_gl_repo_obj(project.creator, repo.repo_sched)


def analyze_data(project, data, commits=False, issues=False, forks=False):
    """IMPORTANT: update the repo role after this call"""
    owner, repository = parse_input_data(data)

    if owner and not repository:
        token = project.creator.gltokens.first()
        if not token:
            return {'status': 'error',
                    'message': 'Token not found for the creator of the project',
                    'code': 400}
        try:
            gitlab_list, git_list = get_gitlab_repos(owner, token.token, forks)
        except Exception as e:
            logging.warning("Error for Gitlab owner {}: {}".format(owner, e))
            return {'status': 'error',
                    'message': 'Error from GitLab API. Does that user exist?',
                    'code': 404}
        if issues:
            for url in gitlab_list:
                url_parsed = url.split('/')
                owner_url = url_parsed[-2]
                repo_url = url_parsed[-1]
                analyze_gitlab(project, owner_url, repo_url)
        if commits:
            for url in git_list:
                git.analyze_git(project, url)
    elif owner and repository:
        if issues:
            token = project.creator.gltokens.first()
            if not token:
                return {'status': 'error',
                        'message': 'Token not found for the creator of the project',
                        'code': 400}
            repo_encoded = '%2F'.join(repository.strip('/').split('/'))
            analyze_gitlab(project, owner, repo_encoded)
        if commits:
            url = f'https://gitlab.com/{owner}/{repository}.git'
            git.analyze_git(project, url)
    else:
        return {'status': 'error',
                'message': "We couldn't guess what do you mean with that string. "
                           "Valid: URL user, URL repo, user, user/repo or user/group/.../repo",
                'code': 400}

    return {'status': 'ok', 'code': 200}


def get_gitlab_repos(owner, token, forks=False):
    """
    Get all the repositories from a owner or a group
    Limited to 5 seconds
    :param owner: Group or user name
    :param token: Token for gitlab authentication. Must be oauth
    :param forks: Get owner forks
    :return: Tuple of list of (gitlab repositories and git repositories)
    """
    init_time = time.time()
    git_urls = list()
    gitlab_urls = list()
    # GROUP REPOSITORIES
    headers = {'Authorization': "Bearer {}".format(token)}
    r_group = requests.get('https://gitlab.com/api/v4/groups/{}'.format(owner), headers=headers)
    if r_group.ok:
        r = requests.get('https://gitlab.com/api/v4/groups/{}/projects?visibility=public'.format(owner),
                         headers=headers)
        if not r.ok:
            raise Exception('Projects not found for that group')
        for project in r.json():
            gitlab_urls.append(project['web_url'])
            git_urls.append(project['http_url_to_repo'])

        gl_urls_sg, git_urls_sg = get_urls_subgroups(owner, init_time, forks)
        gitlab_urls += gl_urls_sg
        git_urls += git_urls_sg
        return gitlab_urls, git_urls

    # USER REPOSITORIES
    r = requests.get("https://gitlab.com/api/v4/search?scope=users&search={}".format(owner), headers=headers)
    if not r.ok or len(r.json()) <= 0:
        raise Exception('User/group not found in GitLab, or the API is not working')
    user = r.json()[0]
    r = requests.get("https://gitlab.com/api/v4/users/{}/projects?visibility=public".format(user['id']),
                     headers=headers)
    if not r.ok:
        raise Exception('Error in GitLab API retrieving user projects')
    for project in r.json():
        if ('forked_from_project' not in project) or forks:
            git_urls.append(project['http_url_to_repo'])
            gitlab_urls.append(project['web_url'])

    return gitlab_urls, git_urls


def get_urls_subgroups(group, init_time=time.time(), forks=False):
    """
    Get repositories from subgroups
    Limited to 6 seconds
    NOTE: Auth token doesn't work with subgroups, no token required here (last update: 07-2019)
    :param group:
    :param init_time: The time it started
    :param forks: get forks
    :return: gl_urls, git_urls
    """
    gitlab_urls, git_urls = list(), list()
    r = requests.get('https://gitlab.com/api/v4/groups/{}/subgroups'.format(group))
    if not r.ok:
        return gitlab_urls, git_urls
    for subgroup in r.json():
        path = "{}%2F{}".format(group, subgroup['path'])
        r = requests.get('https://gitlab.com/api/v4/groups/{}/projects?visibility=public'.format(path))
        if not r.ok:
            continue
        else:
            for project in r.json():
                if ('forked_from_project' not in project) or forks:
                    main_group = project['path_with_namespace'].split('/')[0]
                    subgroup = '%2F'.join(project['path_with_namespace'].split('/')[1:])
                    gitlab_urls.append('https://gitlab.com/{}/{}'.format(main_group, subgroup))
                    git_urls.append(project['http_url_to_repo'])
        gl_urls_sub, git_urls_sub = get_urls_subgroups(path, init_time, forks)
        gitlab_urls += gl_urls_sub
        git_urls += git_urls_sub
        logging.error("Elapsed: {}".format(time.time()-init_time))
        if time.time() > init_time + 6:
            return gitlab_urls, git_urls

    return gitlab_urls, git_urls
