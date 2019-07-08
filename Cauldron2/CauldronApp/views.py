from django.shortcuts import render
from django.http import HttpResponseRedirect, JsonResponse
from django.contrib.auth import login, logout
from django.contrib.auth.models import User

import os
import jwt
import re
import ssl
import logging
import requests
from random import choice
from github import Github
from gitlab import Gitlab
from slugify import slugify
from string import ascii_lowercase, digits
from urllib.parse import urlparse, urlencode
from elasticsearch import Elasticsearch
from elasticsearch.client import CatClient
from elasticsearch.connection import create_ssl_context

from Cauldron2.settings import GH_CLIENT_ID, GH_CLIENT_SECRET, GL_CLIENT_ID, GL_CLIENT_SECRET, \
                                ES_IN_HOST, ES_IN_PORT, ES_IN_PROTO, ES_ADMIN_PSW, \
                                KIB_IN_HOST, KIB_IN_PORT, KIB_IN_PROTO, KIB_OUT_URL, \
                                KIB_PATH
from CauldronApp.models import GithubUser, GitlabUser, Dashboard, Repository, Task, CompletedTask, AnonymousUser, ESUser
from CauldronApp.githubsync import GitHubSync

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

GH_ACCESS_OAUTH = 'https://github.com/login/oauth/access_token'
GH_URI_IDENTITY = 'https://github.com/login/oauth/authorize'

GL_ACCESS_OAUTH = 'https://gitlab.com/oauth/token'
GL_URI_IDENTITY = 'https://gitlab.com/oauth/authorize'
GL_REDIRECT_PATH = '/gitlab-login'

ES_IN_URL = "{}://{}:{}".format(ES_IN_PROTO, ES_IN_HOST, ES_IN_PORT)
KIB_IN_URL = "{}://{}:{}{}".format(KIB_IN_PROTO, KIB_IN_HOST, KIB_IN_PORT, KIB_PATH)


def homepage(request):
    context = create_context(request)

    if request.user.is_authenticated:
        your_dashboards = Dashboard.objects.filter(creator=request.user)
        context_your_dbs = []
        for dash in your_dashboards:
            status = get_dashboard_status(dash.id)

            completed = sum(1 for repo in status['repos'] if repo['status'] == 'COMPLETED')
            context_your_dbs.append({'status': status['general'],
                                     'id': dash.id,
                                     'name': dash.name,
                                     'completed': completed,
                                     'total': len(status['repos'])})
    else:
        context_your_dbs = []

    # TODO: Generate a state for that session and store it in request.session. More security in Oauth
    context['your_dashboards'] = context_your_dbs
    context['gh_uri_identity'] = GH_URI_IDENTITY
    context['gh_client_id'] = GH_CLIENT_ID
    context['gl_uri_identity'] = GL_URI_IDENTITY
    context['gl_client_id'] = GL_CLIENT_ID
    context['gl_uri_redirect'] = "https://{}{}".format(request.get_host(), GL_REDIRECT_PATH)
    context['gitlab_allow'] = hasattr(request.user, 'gitlabuser')
    context['github_allow'] = hasattr(request.user, 'githubuser')

    return render(request, 'index.html', context=context)


# TODO: Add state
def request_github_login_callback(request):
    # Github authentication
    code = request.GET.get('code', None)
    if not code:
        return render(request, 'error.html', status=400,
                      context={'title': 'Bad Request',
                               'description': "There isn't a code in the GitHub callback"})

    r = requests.post(GH_ACCESS_OAUTH,
                      data={'client_id': GH_CLIENT_ID,
                            'client_secret': GH_CLIENT_SECRET,
                            'code': code},
                      headers={'Accept': 'application/json'})
    if r.status_code != requests.codes.ok:
        logging.error('GitHub API error %s %s %s', r.status_code, r.reason, r.text)
        return render(request, 'error.html', status=500,
                      context={'title': 'GitHub error',
                               'description': "GitHub API error"})
    token = r.json().get('access_token', None)
    if not token:
        logging.error('ERROR GitHub Token not found. %s', r.text)
        return render(request, 'error.html', status=500,
                      context={'title': 'GitHub error',
                               'description': "Error getting the token from GitHub endpoint"})

    # Authenticate/register an user, and login
    gh = Github(token)
    gh_user = gh.get_user()
    username = gh_user.login
    photo_url = gh_user.avatar_url

    # Get data from session
    data_add = request.session.get('add_repo', None)
    last_page = request.session.get('last_page', None)

    tricky_authentication(request, GithubUser, username, token, photo_url)

    # Get the previous state
    if data_add:
        dash = Dashboard.objects.filter(id=data_add['dash_id']).first()
        # Only GitHub, is the new account added
        if data_add['backend'] == 'github':
            manage_add_gh_repo(dash, data_add['data'])

    if last_page:
        return HttpResponseRedirect(last_page)

    return HttpResponseRedirect('/')


def merge_accounts(user_origin, user_dest):
    """
    Change the references of that user to another one
    :param user_origin: User to delete
    :param user_dest: User to keep
    :return:
    """
    gh_users = GithubUser.objects.filter(user=user_origin)
    for gh_user in gh_users:
        gh_user.user = user_dest
        gh_user.save()
    gl_users = GitlabUser.objects.filter(user=user_origin)
    for gl_user in gl_users:
        gl_user.user = user_dest
        gl_user.save()
    dashs = Dashboard.objects.filter(creator=user_origin)
    for dash in dashs:
        dash.creator = user_dest
        dash.save()
    tasks = Task.objects.filter(user=user_origin)
    for task in tasks:
        task.user = user_dest
        task.save()
    c_tasks = CompletedTask.objects.filter(user=user_origin)
    for c_task in c_tasks:
        c_task.user = user_dest
        c_task.save()


# TODO: Add state
def request_gitlab_login_callback(request):
    # Gitlab authentication
    code = request.GET.get('code', None)
    if not code:
        return render(request, 'error.html', status=400,
                      context={'title': 'Bad Request',
                               'description': "There isn't a code in the GitLab callback"})
    r = requests.post(GL_ACCESS_OAUTH,
                      params={'client_id': GL_CLIENT_ID,
                              'client_secret': GL_CLIENT_SECRET,
                              'code': code,
                              'grant_type': 'authorization_code',
                              'redirect_uri': "https://{}{}".format(request.get_host(), GL_REDIRECT_PATH)},
                      headers={'Accept': 'application/json'})

    if r.status_code != requests.codes.ok:
        logging.error('Gitlab API error %s %s', r.status_code, r.reason)
        return render(request, 'error.html', status=500,
                      context={'title': 'Gitlab error',
                               'description': "Gitlab API error"})
    token = r.json().get('access_token', None)
    if not token:
        logging.error('ERROR Gitlab Token not found. %s', r.text)
        return render(request, 'error.html', status=500,
                      context={'title': 'Gitlab error',
                               'description': "Error getting the token from Gitlab endpoint"})

    # Authenticate/register an user, and login
    gl = Gitlab(url='https://gitlab.com', oauth_token=token)
    gl.auth()
    username = gl.user.attributes['username']
    photo_url = gl.user.attributes['avatar_url']

    # Get data from session
    data_add = request.session.get('add_repo', None)
    last_page = request.session.get('last_page', None)

    tricky_authentication(request, GitlabUser, username, token, photo_url)

    # Get the previous state
    if data_add:
        dash = Dashboard.objects.filter(id=data_add['dash_id']).first()
        # Only GitLab, is the new account added
        if data_add['backend'] == 'gitlab':
            manage_add_gl_repo(dash, data_add['data'])

    if last_page:
        return HttpResponseRedirect(last_page)

    return HttpResponseRedirect('/')


def tricky_authentication(req, BackendUser, username, token, photo_url):
    """
    Tricky authentication ONLY for login callbacks.
    :param req: request from login callback
    :param BackendUser: GitlabUser, GithubUser... Full model object with the tokens
    :param username: username for the entity
    :param token: token for the entity
    :param photo_url: photo for the user and the entity
    :return:
    """
    ent_user = BackendUser.objects.filter(username=username).first()
    if ent_user:
        dj_ent_user = ent_user.user
    else:
        dj_ent_user = None

    if dj_ent_user:
        # Django Entity user exists, someone is authenticated and not the same account
        if req.user.is_authenticated and dj_ent_user != req.user:
            merge_accounts(req.user, dj_ent_user)
            req.user.delete()
            login(req, dj_ent_user)
        # Django Entity user exists and none is authenticated
        else:
            login(req, dj_ent_user)
        # Update the token
        ent_user.token = token
        ent_user.save()
    else:
        # Django Entity user doesn't exist, someone is authenticated
        if req.user.is_authenticated:
            # Check if is anonymous and delete anonymous tag
            anony_user = AnonymousUser.objects.filter(user=req.user).first()
            if anony_user:
                anony_user.delete()
            # Create the token entry and associate with the account
            gl_entry = BackendUser(user=req.user, username=username, token=token, photo=photo_url)
            gl_entry.save()
        # Django Entity user doesn't exist, none is authenticated
        else:
            # Create account
            dj_user = create_django_user()
            login(req, dj_user)
            # Create the token entry and associate with the account
            gl_entry = BackendUser(user=req.user, username=username, token=token, photo=photo_url)
            gl_entry.save()


def create_django_user():
    """
    Create a django user with a random name and unusable password
    :return: User object
    """
    dj_name = generate_random_uuid(length=96)
    dj_user = User.objects.create_user(username=dj_name)
    dj_user.set_unusable_password()
    dj_user.save()
    return dj_user


def request_logout(request):
    logout(request)
    return HttpResponseRedirect('/')


def request_edit_dashboard(request, dash_id):
    """
    Edit a dashboard. Only POST allowed:
    - data: Could be URL user, URL repo, user, user/repo
    - action: add or delete. If delete: in data field only the URL of a repository is accepted
    - backend: git, github, gitlab. For git only URL is accepted
    :param request: Django request object
    :param dash_id: ID of the dashboard
    :return:
    """
    dash = Dashboard.objects.filter(id=dash_id).first()
    if not dash:
        return JsonResponse({'status': 'error', 'message': 'Dashboard not found'}, status=404)
    if not request.user.is_authenticated:
        return JsonResponse({'status': 'error', 'message': 'You are not authenticated', 'redirect': '/login?next=/dashboard/' + str(dash_id)}, status=401)
    if request.user != dash.creator:
        return JsonResponse({'status': 'error', 'message': 'You cannot edit this dashboard'}, status=403)
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Only POST method allowed'}, status=405)

    # Get the possible data posted
    action = request.POST.get('action', None)
    backend = request.POST.get('backend', None)
    data_in = request.POST.get('data', None)  # Could be url or user

    if not action or action not in ('add', 'delete', 'reanalyze'):
        return JsonResponse({'status': 'error', 'message': 'Action not found in the POST or action not allowed'},
                            status=400)
    if not backend or backend not in ('github', 'gitlab', 'git'):
        return JsonResponse({'status': 'error', 'message': 'Backend not found in the POST or action not allowed'},
                            status=400)
    if not data_in:
        return JsonResponse({'status': 'error', 'message': 'We need a url or a owner to add/delete'},
                            status=400)

    es_user = ESUser.objects.filter(dashboard=dash).first()
    if not es_user:
        return JsonResponse({'status': 'error',
                             'message': 'Internal server error. Kibana user not found for that dashboard'},
                            status=500)

    if action == 'delete':
        repo = Repository.objects.filter(url=data_in, backend=backend).first()
        if not repo:
            return JsonResponse({'status': 'error', 'message': 'Repository not found'},
                                status=404)
        repo.dashboards.remove(dash)
        enriched_indices = get_enriched_indices(repo.index_name, backend)
        delete_role_indices(role_name=es_user.role, indices=enriched_indices)
        task = Task.objects.filter(repository=repo).first()
        if task and task.user == dash.creator and not task.worker_id:
            task.delete()
        return JsonResponse({'status': 'deleted'})

    elif action == 'reanalyze':
        repo = Repository.objects.filter(url=data_in, backend=backend).first()
        if not repo:
            return JsonResponse({'status': 'error', 'message': 'Repository not found'},
                                status=404)
        started = start_task(repo=repo, user=request.user, restart=True)
        if started:
            return JsonResponse({'status': 'reanalyze'})
        else:
            return JsonResponse({'status': 'Running or pending'})

    # From here the action should be add
    if backend == 'git':
        repo = add_to_dashboard(dash, backend, data_in)

        es_user = ESUser.objects.filter(dashboard=dash).first()
        enriched_indices = get_enriched_indices(repo.index_name, backend)
        add_role_indices(es_user.role, enriched_indices)

        start_task(repo, request.user, False)

        return JsonResponse({'status': 'ok'})

    data = guess_data_backend(data_in, backend)
    if not data:
        return JsonResponse({'status': 'error',
                             'message': "We couldn't guess what do you mean with that string. "
                                        "Valid: URL user, URL repo, user or user/repo"},
                            status=401)
    if backend == 'github':
        if not hasattr(request.user, 'githubuser'):
            request.session['add_repo'] = {'data': data, 'backend': backend, 'dash_id': dash.id}
            request.session['last_page'] = '/dashboard/{}'.format(dash_id)
            params = urlencode({'client_id': GH_CLIENT_ID})
            gh_url_oauth = "{}?{}".format(GH_URI_IDENTITY, params)
            return JsonResponse({'status': 'error',
                                 'message': 'We need your GitHub token for analyzing this kind of repositories',
                                 'redirect': gh_url_oauth},
                                status=401)
        return manage_add_gh_repo(dash, data)

    elif backend == 'gitlab':
        if not hasattr(request.user, 'gitlabuser'):
            request.session['add_repo'] = {'data': data, 'backend': backend, 'dash_id': dash.id}
            request.session['last_page'] = '/dashboard/{}'.format(dash_id)
            params = urlencode({'client_id': GL_CLIENT_ID,
                                'response_type': 'code',
                                'redirect_uri': "https://{}{}".format(request.get_host(), GL_REDIRECT_PATH)})
            gh_url_oauth = "{}?{}".format(GL_URI_IDENTITY, params)
            return JsonResponse({'status': 'error',
                                 'message': 'We need your GitLab token for analyzing this kind of repositories',
                                 'redirect': gh_url_oauth},
                                status=401)
        return manage_add_gl_repo(dash, data)

    else:
        return JsonResponse({'status': 'error', 'message': 'Backend not found'},
                            status=400)


def manage_add_gh_repo(dash, data):
    """
    Add a repository or a user in a dashboard
    :param dash: Dashboard object for adding
    :param data: Dictionary with the user or the repository to be added. Format: {'user': 'xxx', 'repository': 'yyy'}
    :return:
    """
    if data['user'] and not data['repository']:
        gh_sync = GitHubSync(dash.creator.githubuser.token)
        try:
            git_list, github_list = gh_sync.get_repo(data['user'], False)
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': 'Error from GitHub API. ' + str(e)},
                                status=500)

        enriched_indices = list()
        for url in github_list:
            repo = add_to_dashboard(dash, 'github', url)
            start_task(repo, dash.creator, False)
            enriched_indices += get_enriched_indices(repo.index_name, 'github')

        for url in git_list:
            repo = add_to_dashboard(dash, 'git', url)
            start_task(repo, dash.creator, False)
            enriched_indices += get_enriched_indices(repo.index_name, 'git')

        es_user = ESUser.objects.filter(dashboard=dash).first()
        add_role_indices(es_user.role, enriched_indices)

        return JsonResponse({'status': 'ok'})

    elif data['user'] and data['repository']:
        url = "https://github.com/{}/{}".format(data['user'], data['repository'])

        repo = add_to_dashboard(dash, 'github', url)
        start_task(repo, dash.creator, False)
        repo = add_to_dashboard(dash, 'git', url)
        start_task(repo, dash.creator, False)

        es_user = ESUser.objects.filter(dashboard=dash).first()
        enriched_indices = get_enriched_indices(repo.index_name, 'github') + \
                           get_enriched_indices(repo.index_name, 'git')
        add_role_indices(es_user.role, enriched_indices)

        return JsonResponse({'status': 'ok'})

    return JsonResponse({'status': 'error', 'message': 'Invalid data posted, something is missing'},
                        status=401)


def manage_add_gl_repo(dash, data):
    """
    Add a repository or a user in a dashboard
    :param dash: Dashboard object for adding
    :param data: Dictionary with the user or the repository to be added. Format: {'user': 'xxx', 'repository': 'yyy'}
    :return:
    """
    if data['user'] and not data['repository']:
        try:
            gitlab_list, git_list = get_gl_repos(data['user'], dash.creator.gitlabuser.token)
        except Exception as e:
            logging.warning("Error for Gitlab owner {}: {}".format(data['user'], e))
            return JsonResponse({'status': 'error', 'message': 'Error from GitLab API. Does that user exist?'},
                                status=500)

        enriched_indices = list()
        for url in gitlab_list:
            repo = add_to_dashboard(dash, 'gitlab', url)
            start_task(repo, dash.creator, False)
            enriched_indices += get_enriched_indices(repo.index_name, 'gitlab')

        for url in git_list:
            repo = add_to_dashboard(dash, 'git', url)
            start_task(repo, dash.creator, False)
            enriched_indices += get_enriched_indices(repo.index_name, 'git')

        es_user = ESUser.objects.filter(dashboard=dash).first()
        add_role_indices(es_user.role, enriched_indices)

        return JsonResponse({'status': 'ok'})

    elif data['url'] and data['repository']:
        url = 'https://gitlab.com/{}/{}'.format(data['user'], data['repository'])

        repo = add_to_dashboard(dash, 'gitlab', url)
        start_task(repo, dash.creator, False)
        repo = add_to_dashboard(dash, 'git', url)
        start_task(repo, dash.creator, False)

        es_user = ESUser.objects.filter(dashboard=dash).first()
        enriched_indices = [get_enriched_indices(repo.index_name, 'gitlab'),
                            get_enriched_indices(repo.index_name, 'git')]
        add_role_indices(es_user.role, enriched_indices)

        return JsonResponse({'status': 'ok'})

    return JsonResponse({'status': 'error', 'message': 'Invalid data posted, something is missing'},
                        status=401)


def guess_data_backend(data_guess, backend):
    """
    Guess the following formats:
    - User: "user"
    - User/Repository: "user/repository"
    - URL of user: "https://backend.com/user"
    - URL of repository: "https://backend.com/user/repository"
    backend: Could be github or gitlab, for git is always the URL
    :return:
    """
    gh_user_regex = '([a-zA-Z0-9](?:[a-zA-Z0-9]|-[a-zA-Z0-9]){1,38})'
    gh_repo_regex = '([a-zA-Z0-9\.\-\_]{1,100})'
    gl_user_regex = '([a-zA-Z0-9_\.][a-zA-Z0-9_\-\.]{1,200}[a-zA-Z0-9_\-]|[a-zA-Z0-9_])'
    gl_repo_regex = '([a-zA-Z0-9_\.][a-zA-Z0-9_\-\.]*[a-zA-Z0-9_\-\.])'
    if backend == 'github':
        re_user = re.match('^{}$'.format(gh_user_regex), data_guess)
        if re_user:
            return {'user': re_user.groups()[0], 'repository': None}
        re_url_user = re.match('^https?://github\.com/{}/?$'.format(gh_user_regex), data_guess)
        if re_url_user:
            return {'user': re_url_user.groups()[0], 'repository': None}
        re_url_repo = re.match('^https?://github\.com/{}/{}(?:.git)?$'.format(gh_user_regex, gh_repo_regex), data_guess)
        if re_url_repo:
            return {'user': re_url_repo.groups()[0], 'repository': re_url_repo.groups()[1]}
        re_user_repo = re.match('^{}/{}$'.format(gh_user_regex, gh_repo_regex), data_guess)
        if re_user_repo:
            return {'user': re_user_repo.groups()[0], 'repository': re_user_repo.groups()[1]}
    elif backend == 'gitlab':
        re_user = re.match('^{}$'.format(gl_user_regex), data_guess)
        if re_user:
            return {'user': re_user.groups()[0], 'repository': None}
        re_url_user = re.match('^https?://gitlab\.com/{}\/?$'.format(gl_user_regex), data_guess)
        if re_url_user:
            return {'user': re_url_user.groups()[0], 'repository': None}
        re_url_repo = re.match('^https?://gitlab\.com/{}/{}(?:.git)?$'.format(gl_user_regex, gl_repo_regex), data_guess)
        if re_url_repo:
            return {'user': re_url_repo.groups()[0], 'repository': re_url_repo.groups()[1]}
        re_user_repo = re.match('{}/{}$'.format(gl_user_regex, gl_repo_regex), data_guess)
        if re_user_repo:
            return {'user': re_user_repo.groups()[0], 'repository': re_user_repo.groups()[1]}
    return None


def request_edit_dashboard_name(request, dash_id):
    """
    Update the name for a dashboard
    :param request: Object from Django
    :param dash_id: ID for the dashboard to change
    :return:
    """
    dash = Dashboard.objects.filter(id=dash_id).first()
    if not dash:
        return JsonResponse({'status': 'error', 'message': 'Dashboard not found'}, status=404)

    if not request.user.is_authenticated:
        return JsonResponse({'status': 'error', 'message': 'You are not authenticated', 'redirect': '/login?next=/dashboard/' + str(dash_id)}, status=401)

    if request.user != dash.creator:
        return JsonResponse({'status': 'error', 'message': 'You cannot edit this dashboard'}, status=403)

    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Only POST method allowed'}, status=405)

    name = request.POST.get('name', None)

    if not name:
        return JsonResponse({'status': 'error', 'message': 'New name not found in the POST or action not allowed'},
                            status=400)

    if len(name) < 4 or len(name) > 32:
        return JsonResponse({'status': 'error', 'message': "The name doesn't fit the allowed length "},
                            status=400)

    if not re.match("^[a-zA-Z\s\d_-]+$", name):
        return JsonResponse({'status': 'No valid name',
                             'message': "Only can contain letters, numbers, underscores, hypens or spaces"},
                            status=400)

    dashboards = Dashboard.objects.filter(creator=request.user)
    for tmp_dash in dashboards:
        if tmp_dash.name == name:
            return JsonResponse({'status': 'Duplicate name', 'message': 'You have the same name in another Dashboard'},
                                status=400)
    old_name = dash.name
    dash.name = name
    dash.save()

    return JsonResponse({'status': 'Ok', 'message': 'Name updated from "{}" to "{}"'.format(old_name, name)})


def start_task(repo, user, restart=False):
    """
    Start a new task for the given repository. If the repository has been analyzed,
    it will not start unless forced with restart
    :param repo: Repository object to analyze
    :param user: User that make the analysis
    :param restart: If the task is not pending or running, start it. Else only start if not completed before
    :return:
    """
    if not Task.objects.filter(repository=repo).first():
        if restart or not CompletedTask.objects.filter(repository=repo).first():
            new_task = Task(repository=repo, user=user)
            new_task.save()
            return True
    return False


def request_new_dashboard(request):
    """
    Create a new dashboard
    Redirect to the edit page for the dashboard
    """
    if request.method != 'POST':
        return render(request, 'error.html', status=405,
                      context={'title': 'Method Not Allowed',
                               'description': "Only POST methods allowed"})

    if not request.user.is_authenticated:
        # Create a user
        dj_name = generate_random_uuid(length=96)
        dj_user = User.objects.create_user(username=dj_name)
        dj_user.set_unusable_password()
        dj_user.save()
        # Annotate as anonymous
        anonym_user = AnonymousUser(user=dj_user)
        anonym_user.save()
        # Log in
        login(request, dj_user)

    # Create a new dashboard
    dash = Dashboard.objects.create(name=generate_random_uuid(length=12), creator=request.user)
    dash.name = "Dashboard {}".format(dash.id)
    dash.save()

    # Create the Kibana user associated to that dashboard
    kib_username = "dashboard{}".format(dash.id)
    kib_pwd = generate_random_uuid(length=32, delimiter='')
    create_kibana_user(kib_username, kib_pwd, dash)
    # TODO: If something is wrong delete the dashboard
    return HttpResponseRedirect('/dashboard/{}'.format(dash.id))


def create_kibana_user(name, psw, dashboard):
    """
    Create ES user, role and Role mapping
    :param name: Name for the user
    :param psw: Password fot the user
    :return:
    """
    logging.info('Creating ES user: <{}>'.format(name))
    headers = {'Content-Type': 'application/json'}
    r = requests.put("{}/_opendistro/_security/api/internalusers/{}".format(ES_IN_URL, name),
                     auth=('admin', ES_ADMIN_PSW),
                     json={"password": psw},
                     verify=False,
                     headers=headers)
    logging.info("{} - {}".format(r.status_code, r.text))
    r.raise_for_status()

    role_name = "role_{}".format(name)
    logging.info('Creating ES role for user: <{}>'.format(name))
    r = requests.put("{}/_opendistro/_security/api/roles/{}".format(ES_IN_URL, role_name),
                     auth=('admin', ES_ADMIN_PSW),
                     json={"indices": {'none':  {"*": ["READ"]}}},
                     verify=False,
                     headers=headers)
    logging.info("{} - {}".format(r.status_code, r.text))
    r.raise_for_status()

    logging.info('Creating ES role mapping for user: <{}>'.format(name))
    r = requests.put("{}/_opendistro/_security/api/rolesmapping/{}".format(ES_IN_URL, role_name),
                     auth=('admin', ES_ADMIN_PSW),
                     json={"users": [name]},
                     verify=False,
                     headers=headers)
    logging.info("{} - {}".format(r.status_code, r.text))
    r.raise_for_status()

    # We need to force the creation of his index by login in
    jwt_token = get_kibana_jwt(name, role_name)
    r = requests.get("{}/?jwtToken={}".format(KIB_IN_URL, jwt_token), verify=False)
    r.raise_for_status()

    # We need the name of the index created
    context = create_ssl_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    es = Elasticsearch([ES_IN_HOST], scheme=ES_IN_PROTO, port=ES_IN_PORT,
                       http_auth=("admin", ES_ADMIN_PSW), ssl_context=context)
    cat = CatClient(es)
    index = cat.indices(index=['.kibana_*_{}'.format(name)], h=["index"]).strip()
    if not index:
        raise Exception('Internal server error. Index not found for that kibana user')

    # We copy the default panels here now
    es.reindex(body={"source": {"index": ".kibana_*_defaultpanels"}, "dest": {"index": index}})

    # Create a default index in the role to avoid warnings
    # in the dashboard if a backend doesn't exist
    # These indices were created in the panels container empty
    data = {'indices': {'git_enrich_default': {'*': ['READ']},
                        'git_aoc_enriched_default': {'*': ['READ']},
                        'github_enrich_default': {'*': ['READ']},
                        'gitlab_enriched_default': {'*': ['READ']}
                        }
            }
    r = requests.patch("{}/_opendistro/_security/api/roles".format(ES_IN_URL),
                       auth=('admin', ES_ADMIN_PSW),
                       json=[{"op": "add", "path": "/{}".format(role_name), "value": data}],
                       verify=False,
                       headers=headers)

    es_user = ESUser(name=name, password=psw, role=role_name, dashboard=dashboard, index=index)
    es_user.save()


def add_to_dashboard(dash, backend, url):
    """
    Add a repository to a dashboard
    :param dash: Dashboard row from db
    :param url: url for the analysis
    :param backend: Identity used like github or gitlab. See models.py for more details
    :return: Repository created
    """
    repo_obj = Repository.objects.filter(url=url, backend=backend).first()
    if not repo_obj:
        index_name = create_index_name(backend, url)
        repo_obj = Repository(url=url, backend=backend, index_name=index_name)
        repo_obj.save()
    repo_obj.dashboards.add(dash)
    return repo_obj


def get_enriched_indices(index_name, backend):
    """
    Return the names of the enriched indices
    :param index_name: The index global name for that repository
    :param backend: Git, GitHub or GitLab
    :return: A list with the names of the indices
    """
    if backend == 'git':
        return ["git_aoc_enriched_{}".format(index_name), "git_enrich_{}".format(index_name)]
    elif backend == 'github':
        return ["github_enrich_{}".format(index_name)]
    elif backend == 'gitlab':
        return ["gitlab_enriched_{}".format(index_name)]
    raise Exception('Unknown backend')


def create_es_indices(indices):
    """
    Create the indices in ElasticSearch
    :param indices: List of indices
    :return:
    """
    # Connect ElasticSearch
    context = create_ssl_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    es = Elasticsearch([ES_IN_HOST], scheme=ES_IN_PROTO, port=ES_IN_PORT,
                       http_auth=("admin", ES_ADMIN_PSW), ssl_context=context)
    for index in indices:
        es.indices.create(index, ignore=400)


def create_index_name(backend, url):
    if backend in ('github', 'gitlab'):
        owner, repo = parse_url(url)
        return slugify("{}_{}_{}".format(backend, owner, repo), max_length=100, replacements=[['.', '_dot_']]).lower()
    else:
        # Like git
        try:
            owner, repo = parse_url(url)
            txt = slugify("{}_{}_{}".format('git', owner, repo), max_length=100, replacements=[['.', '_dot_']]).lower()
        except Exception:
            txt = slugify("{}_{}".format('git', url), max_length=100, replacements=[['.', '_dot_']]).lower()

        return txt


def add_role_indices(role_name, indices):
    """
    Add multiple indices to a role
    :param role_name:
    :param indices:
    :return:
    """
    headers = {'Content-Type': 'application/json'}
    r = requests.get("{}/_opendistro/_security/api/roles/{}".format(ES_IN_URL, role_name),
                     auth=('admin', ES_ADMIN_PSW),
                     verify=False,
                     headers=headers)
    data = r.json()
    if role_name not in data:
        data[role_name] = dict()
        data[role_name]['indices'] = dict()
    for index in indices:
        if index not in data[role_name]['indices']:
            data[role_name]['indices'][index] = {'*': ['READ']}

    r = requests.patch("{}/_opendistro/_security/api/roles".format(ES_IN_URL),
                       auth=('admin', ES_ADMIN_PSW),
                       json=[{"op": "add", "path": "/{}".format(role_name), "value": data[role_name]}],
                       verify=False,
                       headers=headers)
    r.raise_for_status()


def delete_role_indices(role_name, indices):
    """
    Delete multiple indices from a role
    :param role_name:
    :param indices:
    :return:
    """
    items = list()
    for index in indices:
        items.append({"op": "remove",
                      "path": "/indices/{}".format(index)
                      })
    headers = {'Content-Type': 'application/json'}
    r = requests.patch("{}/_opendistro/_security/api/roles/{}".format(ES_IN_URL, role_name),
                       auth=('admin', ES_ADMIN_PSW),
                       json=items,
                       verify=False,
                       headers=headers)
    r.raise_for_status()


def get_dashboard_status(dash_id):
    """
    General status:
    If no repos -> UNKNOWN
    1. If any repo is running -> return RUNNING
    2. Else if any repo pending -> return PENDING
    3. Else if any repo error -> return ERROR
    4. Else -> return COMPLETED
    :param dash_id: id of the dashboard
    :return: Status of the dashboard depending on the the previous rules
    """
    repos = Repository.objects.filter(dashboards__id=dash_id)
    if len(repos) == 0:
        return {
            'repos': [],
            'general': 'UNKNOWN',
            'exists': False
        }
    status = {
        'repos': [],
        'general': 'UNKNOWN',
        'exists': True
    }
    for repo in repos:
        status_repo = get_repo_status(repo)
        status['repos'].append({'id': repo.id, 'status': status_repo})

    status['general'] = general_stat_dash(repos)

    return status


def general_stat_dash(repos):
    """
    General status from repos rows
    :param repos: list of repos from database
    :return:
    """
    general = 'UNKNOWN'
    for repo in repos:
        status_repo = get_repo_status(repo)

        if status_repo == 'RUNNING':
            general = 'RUNNING'
        elif status_repo == 'PENDING' and (general != 'RUNNING'):
            general = 'PENDING'
        elif (status_repo == 'ERROR') and (general not in ('RUNNING', 'PENDING')):
            general = 'ERROR'
        elif (status_repo == 'COMPLETED') and (general not in ('RUNNING', 'PENDING', 'ERROR')):
            general = 'COMPLETED'
        # Unknown status not included
    return general


def get_dashboard_info(dash_id):
    """
    Get information about the repositories that are analyzed / being analyzed
    :param dash_id: id of the dashboard
    :return:
    """
    info = {
        'repos': list(),
        'exists': True
    }
    repos = Repository.objects.filter(dashboards__id=dash_id)

    info['general'] = general_stat_dash(repos)
    if len(repos) == 0:
        info['exists'] = False
        return info

    for repo in repos:
        item = dict()
        item['id'] = repo.id
        item['url'] = repo.url
        item['backend'] = repo.backend
        item['status'] = get_repo_status(repo)

        task = Task.objects.filter(repository=repo).first()
        compl_task = CompletedTask.objects.filter(repository=repo).order_by('-completed').first()
        if task:
            item['created'] = task.created
            item['started'] = task.started
            if compl_task:
                item['completed'] = compl_task.completed
            else:
                item['completed'] = None

        elif compl_task and not task:
            item['created'] = compl_task.created
            item['started'] = compl_task.started
            item['completed'] = compl_task.completed

        else:
            item['created'] = None
            item['started'] = None
            item['completed'] = None
        info['repos'].append(item)

    return info


def request_show_dashboard(request, dash_id):
    """
    View for a dashboard. It can be editable if the user is authenticated and is the creator
    :param request:
    :param dash_id:
    :return:
    """
    if request.method != 'GET':
        return render(request, 'error.html', status=405,
                      context={'title': 'Method Not Allowed',
                               'description': "Only GET methods allowed"})

    dash = Dashboard.objects.filter(id=dash_id).first()
    if not dash:
        return render(request, 'error.html', status=405,
                      context={'title': 'Dashboard not found',
                               'description': "This dashboard was not found in this server"})

    # CREATE RESPONSE
    context = create_context(request)
    # Information for the dashboard
    if dash:
        context['dashboard'] = dash
        context['repositories'] = Repository.objects.filter(dashboards__id=dash_id).order_by('-id')

    context['editable'] = request.user.is_authenticated and request.user == dash.creator
    context['dash_id'] = dash_id

    return render(request, 'dashboard.html', context=context)


def request_kibana(request, dash_id):
    """
    Redirect to Kibana
    :param request:
    :param dash_id:
    :return:
    """
    dash = Dashboard.objects.filter(id=dash_id).first()
    if not dash:
        return JsonResponse({'status': 'error', 'message': 'Dashboard not found'}, status=404)

    if not request.user.is_authenticated:
        return JsonResponse({'status': 'error', 'message': 'You are not authenticated'}, status=401)

    if request.user != dash.creator:
        return JsonResponse({'status': 'error', 'message': 'This is not your dashboard'}, status=403)

    if request.method != 'GET':
        return JsonResponse({'status': 'error', 'message': 'Only GET method allowed'}, status=405)

    es_user = ESUser.objects.filter(dashboard=dash).first()
    if not es_user:
        return JsonResponse({'status': 'error', 'message': 'Internal server error. Kibana user for that dashboard not found'}, status=500)
    jwt_key = get_kibana_jwt(es_user.name, es_user.role)

    return HttpResponseRedirect(KIB_OUT_URL + "/?jwtToken=" + jwt_key)


def get_kibana_jwt(user, roles):
    """
    Return the jwt key for a specific user and role
    :param user:
    :param roles: String or list of roles
    :return:
    """
    dirname = os.path.dirname(os.path.abspath(__file__))
    key_location = os.path.join(dirname, 'jwtR256.key')
    with open(key_location, 'r') as f_private:
        private_key = f_private.read()
    claims = {
        "user": user,
        "roles": roles
    }
    return jwt.encode(claims, private_key, algorithm='RS256').decode('utf-8')


def request_delete_token(request):
    """
    Function for deleting a token from a user.
    It deletes the tasks associate with that token
    :param request
    :return:
    """
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Only POST methods allowed'}, status=405)

    if not request.user.is_authenticated:
        return JsonResponse({'status': 'error', 'message': 'You are not logged in'}, status=401)

    identity = request.POST.get('identity', None)
    if identity == 'github':
        if hasattr(request.user, 'githubuser'):
            request.user.githubuser.delete()
            tasks = Task.objects.filter(user=request.user)
            for task in tasks:
                if task.repository.backend == 'github':
                    task.delete()
        return JsonResponse({'status': 'ok'})

    elif identity == 'gitlab':
        if hasattr(request.user, 'gitlabuser'):
            request.user.gitlabuser.delete()
            tasks = Task.objects.filter(user=request.user)
            for task in tasks:
                if task.repository.backend == 'gitlab':
                    task.delete()
        return JsonResponse({'status': 'ok'})
    else:
        return JsonResponse({'status': 'error', 'message': 'Unkown identity: {}'.format(identity)})


def create_context(request):
    """
    Create a new context dict with some common information among views
    :param request:
    :return:
    """
    context = dict()

    # Generate information for identities
    context['gh_uri_identity'] = GH_URI_IDENTITY
    context['gh_client_id'] = GH_CLIENT_ID
    context['gl_uri_identity'] = GL_URI_IDENTITY
    context['gl_client_id'] = GL_CLIENT_ID
    context['gl_uri_redirect'] = "https://{}{}".format(request.get_host(), GL_REDIRECT_PATH)

    # Information for the photo and the profile
    context['authenticated'] = request.user.is_authenticated
    if hasattr(request.user, 'githubuser'):
        context['auth_user_username'] = request.user.githubuser.username
        context['photo_user'] = request.user.githubuser.photo
    elif hasattr(request.user, 'gitlabuser'):
        context['auth_user_username'] = request.user.gitlabuser.username
        context['photo_user'] = request.user.gitlabuser.photo
    else:
        context['auth_user_username'] = 'Anonymous'
        context['photo_user'] = '/static/img/profile-default.png'

    # Information about the accounts connected
    context['github_enabled'] = hasattr(request.user, 'githubuser')
    context['gitlab_enabled'] = hasattr(request.user, 'gitlabuser')

    return context


def repo_status(request, repo_id):
    if request.method != 'GET':
        return render(request, 'error.html', status=405,
                      context={'title': 'Method Not Allowed',
                               'description': "Only GET methods allowed"})
    repo = Repository.objects.filter(id=repo_id).first()
    if not repo:
        return JsonResponse({'status': 'UNKNOWN'})
    return JsonResponse({'status': get_repo_status(repo)})


def request_dash_info(request, dash_id):
    info = get_dashboard_info(dash_id)
    return JsonResponse(info)


def repo_logs(request, repo_id):
    """
    Get the latest logs for a repository
    :param request:
    :param repo_id: Repository Identifier
    :return: Dict{exists[True or False], content[string or None], more[True or False]}
    """
    repo = Repository.objects.filter(id=repo_id).first()
    if not repo:
        return JsonResponse({'content': "Repository not found. Contact us if is an error.", 'more': False})

    task = Task.objects.filter(repository=repo).first()
    if task:
        more = True
        if not task.log_file or not os.path.isfile(task.log_file):
            output = "Logs not found. Has the task started?"
        else:
            output = open(task.log_file, 'r').read() + '\n'

    else:
        more = False
        task = CompletedTask.objects.filter(repository=repo).order_by('completed').last()
        if not task or not task.log_file or not os.path.isfile(task.log_file):
            output = "Logs not found. Maybe it has been deleted. Sorry for the inconveniences"
        else:
            output = open(task.log_file, 'r').read() + '\n'

    response = {
        'content': output,
        'more': more
    }
    return JsonResponse(response)


def parse_url(url):
    """
    Should be validated by valid_github_url
    :param url:
    :return:
    """
    o = urlparse(url)
    return o.path.split('/')[1:]


def valid_github_url(url):
    o = urlparse(url)
    return (o.scheme == 'https' and
            o.netloc == 'github.com' and
            len(o.path.split('/')) == 3)


def valid_gitlab_url(url):
    o = urlparse(url)
    return (o.scheme == 'https' and
            o.netloc == 'gitlab.com' and
            len(o.path.split('/')) == 3)


def get_repo_status(repo):
    """
    Check if there is a task associated or it has been completed
    :param repo: Repository object from the database
    :return: status (PENDING, RUNNING, COMPLETED)
    """
    if hasattr(repo, 'task'):
        # PENDING OR RUNNING
        if repo.task.worker_id:
            return 'RUNNING'
        else:
            return 'PENDING'
    c_task = CompletedTask.objects.filter(repository=repo).order_by('completed').last()
    if c_task:
        return c_task.status
    else:
        return 'UNKNOWN'


def get_gl_repos(owner, token):
    gl = Gitlab(url='https://gitlab.com', oauth_token=token)
    gl.auth()
    users = gl.users.list(username=owner)
    if len(users) > 0:
        user = users[0]
    else:
        user = gl.groups.get(owner)

    repos = user.projects.list(visibility='public')
    git_urls = list()
    gl_urls = list()
    for repo in repos:
        git_urls.append(repo.http_url_to_repo)
        gl_urls.append(repo.web_url)
    return gl_urls, git_urls


# https://gist.github.com/jcinis/2866253
def generate_random_uuid(length=16, chars=ascii_lowercase + digits, split=4, delimiter='-'):

    username = ''.join([choice(chars) for i in range(length)])

    if split:
        username = delimiter.join([username[start:start + split] for start in range(0, len(username), split)])

    try:
        User.objects.get(username=username)
        return generate_random_uuid(length=length, chars=chars, split=split, delimiter=delimiter)
    except User.DoesNotExist:
        return username
