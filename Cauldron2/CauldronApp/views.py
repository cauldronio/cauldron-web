from django.shortcuts import render
from django.http import HttpResponseRedirect, JsonResponse
from django.contrib.auth import login, logout
from django.contrib.auth.models import User
from django.urls import reverse
from django.db import transaction
from django.db.models import Count, F

import os
import jwt
import re
import logging
import requests
from random import choice
from github import Github
from gitlab import Gitlab
from string import ascii_lowercase, digits
from urllib.parse import urlparse, urlencode
import time

from Cauldron2.settings import GH_CLIENT_ID, GH_CLIENT_SECRET, GL_CLIENT_ID, GL_CLIENT_SECRET, \
                                MEETUP_CLIENT_ID, MEETUP_CLIENT_SECRET, \
                                ES_IN_HOST, ES_IN_PORT, ES_IN_PROTO, ES_ADMIN_PSW, \
                                KIB_IN_HOST, KIB_IN_PORT, KIB_IN_PROTO, KIB_OUT_URL, \
                                KIB_PATH, HATSTALL_ENABLED, HATSTALL_URL, GOOGLE_ANALYTICS_ID
from CauldronApp.models import GithubUser, GitlabUser, MeetupUser, Dashboard, Repository, Task, \
                               CompletedTask, AnonymousUser, ESUser, Token
from CauldronApp.githubsync import GitHubSync
from CauldronApp.opendistro_utils import OpendistroApi

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

GH_ACCESS_OAUTH = 'https://github.com/login/oauth/access_token'
GH_URI_IDENTITY = 'https://github.com/login/oauth/authorize'

GL_ACCESS_OAUTH = 'https://gitlab.com/oauth/token'
GL_URI_IDENTITY = 'https://gitlab.com/oauth/authorize'
GL_REDIRECT_PATH = '/gitlab-login'

MEETUP_ACCESS_OAUTH = 'https://secure.meetup.com/oauth2/access'
MEETUP_URI_IDENTITY = 'https://secure.meetup.com/oauth2/authorize'
MEETUP_REDIRECT_PATH = '/meetup-login'

DASHBOARD_LOGS = '/dashboard_logs'

BACKEND_INDICES = [
    {
        "name": "git_aoc_enriched_index",
        "backend": "git",
        "url_field": "repository"
    },
    {
        "name": "git_enrich_index",
        "backend": "git",
        "url_field": "repo_name"
    },
    {
        "name": "github_enrich_index",
        "backend": "github",
        "url_field": "repository"
    },
    {
        "name": "gitlab_enriched_index",
        "backend": "gitlab",
        "url_field": "repository"
    },
    {
        "name": "meetup_enriched_index",
        "backend": "meetup",
        "url_field": "tag"
    },
]


ES_IN_URL = "{}://{}:{}".format(ES_IN_PROTO, ES_IN_HOST, ES_IN_PORT)
KIB_IN_URL = "{}://{}:{}{}".format(KIB_IN_PROTO, KIB_IN_HOST, KIB_IN_PORT, KIB_PATH)

ES_INDEX_SUFFIX = "index"

logger = logging.getLogger(__name__)


def homepage(request):
    context = create_context(request)

    return render(request, 'index.html', context=context)


def request_user_projects(request):
    context = create_context(request)
    if not request.user.is_authenticated:
        context['title'] = "You are not logged in"
        context['description'] = "You need to login or create a new project to continue"
        return render(request, 'error.html', status=400, context=context)
    else:
        projects = Dashboard.objects.filter(creator=request.user)
        projects_info = list()
        for project in projects:
            repositories = Repository.objects.filter(dashboards=project.pk)
            n_completed = CompletedTask.objects.filter(repository__in=repositories, status='COMPLETED', old=False).count()
            n_errors = CompletedTask.objects.filter(repository__in=repositories, status='ERROR', old=False).count()
            n_pending = Task.objects.filter(repository__in=repositories).count()
            projects_info.append({
                'project': project,
                'completed': n_completed,
                'errors': n_errors,
                'pending': n_pending,
                'total': n_completed + n_errors + n_pending
            })
        context['projects_info'] = projects_info
    return render(request, 'projects.html', context=context)


# TODO: Add state
def request_github_login_callback(request):
    context = create_context(request)

    # Github authentication
    code = request.GET.get('code', None)
    if not code:
        context['title'] = "Bad Request"
        context['description'] = "There isn't a code in the GitHub callback"
        return render(request, 'error.html', status=400,
                      context=context)

    r = requests.post(GH_ACCESS_OAUTH,
                      data={'client_id': GH_CLIENT_ID,
                            'client_secret': GH_CLIENT_SECRET,
                            'code': code},
                      headers={'Accept': 'application/json'})
    if r.status_code != requests.codes.ok:
        logging.error('GitHub API error %s %s %s', r.status_code, r.reason, r.text)
        context['title'] = "GitHub error"
        context['description'] = "GitHub API error"
        return render(request, 'error.html', status=500,
                      context=context)
    token = r.json().get('access_token', None)
    if not token:
        logging.error('ERROR GitHub Token not found. %s', r.text)
        context['title'] = "GitHub error"
        context['description'] = "Error getting the token from GitHub endpoint"
        return render(request, 'error.html', status=500,
                      context=context)

    # Authenticate/register an user, and login
    gh = Github(token)
    gh_user = gh.get_user()
    username = gh_user.login
    photo_url = gh_user.avatar_url

    # Get data from session
    data_add = request.session.get('add_repo', None)
    last_page = request.session.get('last_page', None)

    tricky_authentication(request, GithubUser, username, username, token, photo_url)

    # Get the previous state
    if data_add:
        dash = Dashboard.objects.filter(id=data_add['dash_id']).first()
        # Only GitHub, is the new account added
        if data_add['backend'] == 'github':
            commits = data_add['commits']
            issues = data_add['issues']
            manage_add_gh_repo(dash, data_add['data'], commits, issues)

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
    mu_users = MeetupUser.objects.filter(user=user_origin)
    for mu_user in mu_users:
        mu_user.user = user_dest
        mu_user.save()
    dashs = Dashboard.objects.filter(creator=user_origin)
    for dash in dashs:
        dash.creator = user_dest
        dash.save()
    tokens = Token.objects.filter(user=user_origin)
    for token in tokens:
        token.user = user_dest
        token.save()


# TODO: Add state
def request_gitlab_login_callback(request):
    context = create_context(request)

    # Gitlab authentication
    code = request.GET.get('code', None)
    if not code:
        context['title'] = "Bad Request"
        context['description'] = "There isn't a code in the GitLab callback"
        return render(request, 'error.html', status=400,
                      context=context)
    r = requests.post(GL_ACCESS_OAUTH,
                      params={'client_id': GL_CLIENT_ID,
                              'client_secret': GL_CLIENT_SECRET,
                              'code': code,
                              'grant_type': 'authorization_code',
                              'redirect_uri': "https://{}{}".format(request.get_host(), GL_REDIRECT_PATH)},
                      headers={'Accept': 'application/json'})

    if r.status_code != requests.codes.ok:
        logging.error('Gitlab API error %s %s', r.status_code, r.reason)
        context['title'] = "Gitlab error"
        context['description'] = "Gitlab API error"
        return render(request, 'error.html', status=500,
                      context=context)
    token = r.json().get('access_token', None)
    if not token:
        logging.error('ERROR Gitlab Token not found. %s', r.text)
        context['title'] = "Gitlab error"
        context['description'] = "Error getting the token from Gitlab endpoint"
        return render(request, 'error.html', status=500,
                      context=context)

    # Authenticate/register an user, and login
    gl = Gitlab(url='https://gitlab.com', oauth_token=token)
    gl.auth()
    username = gl.user.attributes['username']
    photo_url = gl.user.attributes['avatar_url']

    # Get data from session
    data_add = request.session.get('add_repo', None)
    last_page = request.session.get('last_page', None)

    tricky_authentication(request, GitlabUser, username, username, token, photo_url)

    # Get the previous state
    if data_add:
        dash = Dashboard.objects.filter(id=data_add['dash_id']).first()
        # Only GitLab, is the new account added
        if data_add['backend'] == 'gitlab':
            commits = data_add['commits']
            issues = data_add['issues']
            manage_add_gl_repo(dash, data_add['data'], commits, issues)

    if last_page:
        return HttpResponseRedirect(last_page)

    return HttpResponseRedirect('/')


# TODO: Add state
def request_meetup_login_callback(request):
    context = create_context(request)

    # Meetup authentication
    error = request.GET.get('error', None)
    if error:
        context['title'] = "Error from Meetup Oauth"
        context['description'] = error
        return render(request, 'error.html', status=400,
                      context=context)
    code = request.GET.get('code', None)
    if not code:
        context['title'] = "Bad Request"
        context['description'] = "There isn't a code in the Meetup callback"
        return render(request, 'error.html', status=400,
                      context=context)
    r = requests.post(MEETUP_ACCESS_OAUTH,
                      params={'client_id': MEETUP_CLIENT_ID,
                              'client_secret': MEETUP_CLIENT_SECRET,
                              'code': code,
                              'grant_type': 'authorization_code',
                              'redirect_uri': "https://{}{}".format(request.get_host(), MEETUP_REDIRECT_PATH)},
                      headers={'Accept': 'application/json'})

    if r.status_code != requests.codes.ok:
        logging.error('Meetup API error %s %s', r.status_code, r.reason)
        context['title'] = "Meetup error"
        context['description'] = "Meetup API error"
        return render(request, 'error.html', status=500,
                      context=context)
    response = r.json()
    token = response.get('access_token', None)
    refresh_token = response.get('refresh_token', None)
    if not token or not refresh_token:
        logging.error('ERROR Meetup Token not found. %s', r.text)
        context['title'] = "Meetup error"
        context['description'] = "Error getting the token from Meetup endpoint"
        return render(request, 'error.html', status=500,
                      context=context)

    # Authenticate/register an user, and login
    r = requests.get('https://api.meetup.com/members/self?&sign=true&photo-host=public',
                     headers={'Authorization': 'bearer {}'.format(token)})
    data_user = r.json()
    try:
        photo = data_user['photo']['photo_link']
    except KeyError:
        photo = '/static/img/profile-default.png'

    # Get data from session
    data_add = request.session.get('add_repo', None)
    last_page = request.session.get('last_page', None)

    tricky_authentication(request, MeetupUser, data_user['id'], data_user['name'], token, photo)
    request.user.meetupuser.refresh_token = refresh_token
    request.user.meetupuser.save()
    # Get the previous state
    if data_add:
        dash = Dashboard.objects.filter(id=data_add['dash_id']).first()
        if data_add['backend'] == 'meetup':
            manage_add_meetup_repo(dash, data_add['data'])

    if last_page:
        return HttpResponseRedirect(last_page)

    return HttpResponseRedirect('/')


def tricky_authentication(req, BackendUser, username, name, token, photo_url):
    """
    Tricky authentication ONLY for login callbacks.
    :param req: request from login callback
    :param BackendUser: GitlabUser, GithubUser, MeetupUser... Full model object with the tokens
    :param username: username for the entity
    :param name: name of the user
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
        if req.user.is_authenticated and dj_ent_user != req.user:
            # Django Entity user exists, someone is authenticated and not the same account
            merge_accounts(req.user, dj_ent_user)
            req.user.delete()
            login(req, dj_ent_user)
        else:
            # Django Entity user exists and none is authenticated
            login(req, dj_ent_user)
        # Update the token
        ent_user.token.key = token
        ent_user.token.save()
    else:
        if req.user.is_authenticated:
            # Django Entity user doesn't exist, someone is authenticated
            # Check if is anonymous and delete anonymous tag
            anony_user = AnonymousUser.objects.filter(user=req.user).first()
            if anony_user:
                anony_user.delete()
                req.user.first_name = name
                req.user.save()
        # Django Entity user doesn't exist, none is authenticated
        else:
            # Create account
            dj_user = create_django_user(name)
            login(req, dj_user)
        # Create the token entry
        if BackendUser is GitlabUser:
            token_item = Token(backend='gitlab', key=token, user=req.user)
            token_item.save()
        elif BackendUser is GithubUser:
            token_item = Token(backend='github', key=token, user=req.user)
            token_item.save()
        elif BackendUser is MeetupUser:
            token_item = Token(backend='meetup', key=token, user=req.user)
            token_item.save()
        else:
            raise Exception("Internal server error, BackendUser unknown")

        # Create the BackendUser entry and associate with the account
        bu_entry = BackendUser(user=req.user, username=username, token=token_item, photo=photo_url)
        bu_entry.save()


def create_django_user(name):
    """
    Create a django user with a random name and unusable password
    :name: first_name for the user
    :return: User object
    """
    dj_name = generate_random_uuid(length=96)
    dj_user = User.objects.create_user(username=dj_name, first_name=name)
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
    - backend: git, github, gitlab or meetup. For git only URL is accepted
    :param request: Django request object
    :param dash_id: ID of the dashboard
    :return:
    """
    dash = Dashboard.objects.filter(id=dash_id).first()
    if not dash:
        return JsonResponse({'status': 'error', 'message': 'Dashboard not found'}, status=404)
    if not request.user.is_authenticated:
        return JsonResponse({'status': 'error', 'message': 'You are not authenticated',
                             'redirect': '/login?next=/dashboard/' + str(dash_id)}, status=401)
    if request.user != dash.creator and not request.user.is_superuser:
        return JsonResponse({'status': 'error', 'message': 'You cannot edit this dashboard'}, status=403)
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Only POST method allowed'}, status=405)

    # Get the possible data posted
    action = request.POST.get('action', None)
    backend = request.POST.get('backend', None)
    data_in = request.POST.get('data', None)  # Could be url or user

    if not action or action not in ('add', 'delete', 'reanalyze', 'reanalyze-all'):
        return JsonResponse({'status': 'error', 'message': 'Action not found in the POST or action not allowed'},
                            status=400)
    if not backend or backend not in ('github', 'gitlab', 'meetup', 'git', 'all'):
        return JsonResponse({'status': 'error', 'message': 'Backend not found in the POST or action not allowed'},
                            status=400)
    if not data_in:
        return JsonResponse({'status': 'error', 'message': 'We need a url or a owner to add/delete'},
                            status=400)

    es_users = ESUser.objects.filter(dashboard=dash)
    if len(es_users) != 2:
        logger.error("We didn't find 2 ES users: {}", es_users)
        return JsonResponse({'status': 'error',
                             'message': 'Internal server error. Kibana user not found for that dashboard'},
                            status=500)

    if action == 'delete':
        repo = Repository.objects.filter(id=data_in, backend=backend).first()
        if not repo:
            return JsonResponse({'status': 'error', 'message': 'Repository not found'},
                                status=404)
        repo.dashboards.remove(dash)
        update_role_dashboard(es_users.first().role, dash)
        if backend != 'git':
            task = Task.objects.filter(repository=repo, tokens__user=dash.creator).first()
            if task and not task.worker_id:
                task.delete()
        return JsonResponse({'status': 'deleted'})

    elif action == 'reanalyze':
        repo = Repository.objects.filter(id=data_in, backend=backend).first()
        token = Token.objects.filter(user=dash.creator, backend=backend).first()
        if not repo:
            return JsonResponse({'status': 'error', 'message': 'Repository not found'},
                                status=404)
        elif not token and backend != 'git':
            return JsonResponse({'status': 'error', 'message': 'Token not found for that backend'},
                                status=404)
        started = start_task(repo=repo, token=token)
        if started:
            return JsonResponse({'status': 'reanalyze'})
        else:
            return JsonResponse({'status': 'Running or pending'})

    elif action == 'reanalyze-all':
        repos = Repository.objects.filter(dashboards=dash_id)
        if not repos:
            return JsonResponse({'status': 'error', 'message': 'Repositories not found'},
                                status=404)
        refreshed_count = 0
        for repo in repos:
            token = Token.objects.filter(user=dash.creator, backend=repo.backend).first()
            if token or repo.backend == 'git':
                started = start_task(repo=repo, token=token)
                if started:
                    refreshed_count += 1
        return JsonResponse({'status': 'reanalyze',
                             'message': "{} of {} will be refreshed".format(refreshed_count, len(repos))})

    # From here the action should be add
    if backend == 'git':
        # Remove the spaces to avoid errors
        data = data_in.strip()
        repo = add_to_dashboard(dash, backend, data)
        es_users = ESUser.objects.filter(dashboard=dash)
        update_role_dashboard(es_users.first().role, dash)
        start_task(repo=repo, token=None)

        return JsonResponse({'status': 'ok'})

    data = guess_data_backend(data_in, backend)
    if not data:
        return JsonResponse({'status': 'error',
                             'message': "We couldn't guess what do you mean with that string. "
                                        "Valid: URL user, URL repo, user or user/repo"},
                            status=401)
    if backend == 'github':
        analyze_commits = 'commits' in request.POST
        analyze_issues = 'issues' in request.POST
        if not hasattr(dash.creator, 'githubuser'):
            if request.user != dash.creator:
                # Admin and owner didn't add his token
                return JsonResponse({'status': 'error',
                                     'message': 'Dashboard owner needs a GitHub token '
                                                'to analyze this kind of repositories'},
                                    status=401)
            request.session['add_repo'] = {'data': data,
                                           'backend': backend,
                                           'dash_id': dash.id,
                                           'commits': analyze_commits,
                                           'issues': analyze_issues}
            request.session['last_page'] = '/dashboard/{}'.format(dash_id)
            params = urlencode({'client_id': GH_CLIENT_ID})
            gh_url_oauth = "{}?{}".format(GH_URI_IDENTITY, params)
            return JsonResponse({'status': 'error',
                                 'message': 'We need your GitHub token for analyzing this kind of repositories',
                                 'redirect': gh_url_oauth},
                                status=401)
        return manage_add_gh_repo(dash, data, analyze_commits, analyze_issues)

    elif backend == 'gitlab':
        analyze_commits = 'commits' in request.POST
        analyze_issues = 'issues' in request.POST
        if not hasattr(dash.creator, 'gitlabuser'):
            if request.user != dash.creator:
                return JsonResponse({'status': 'error',
                                     'message': 'Dashboard owner needs a GitLab token to '
                                                'analyze this kind of repositories'},
                                    status=401)
            request.session['add_repo'] = {'data': data,
                                           'backend': backend,
                                           'dash_id': dash.id,
                                           'commits': analyze_commits,
                                           'issues': analyze_issues}
            request.session['last_page'] = '/dashboard/{}'.format(dash_id)
            params = urlencode({'client_id': GL_CLIENT_ID,
                                'response_type': 'code',
                                'redirect_uri': "https://{}{}".format(request.get_host(), GL_REDIRECT_PATH)})
            gl_url_oauth = "{}?{}".format(GL_URI_IDENTITY, params)
            return JsonResponse({'status': 'error',
                                 'message': 'We need your GitLab token for analyzing this kind of repositories',
                                 'redirect': gl_url_oauth},
                                status=401)
        return manage_add_gl_repo(dash, data, analyze_commits, analyze_issues)

    elif backend == 'meetup':
        if not hasattr(dash.creator, 'meetupuser'):
            if request.user != dash.creator:
                return JsonResponse({'status': 'error',
                                     'message': 'Dashboard owner needs a Meetup token to'
                                                ' analyze this kind of repositories'},
                                    status=401)
            request.session['add_repo'] = {'data': data, 'backend': backend, 'dash_id': dash.id}
            request.session['last_page'] = '/dashboard/{}'.format(dash_id)
            params = urlencode({'client_id': MEETUP_CLIENT_ID,
                                'response_type': 'code',
                                'redirect_uri': "https://{}{}".format(request.get_host(), MEETUP_REDIRECT_PATH)})
            meetup_url_oauth = "{}?{}".format(MEETUP_URI_IDENTITY, params)
            return JsonResponse({'status': 'error',
                                 'message': 'We need your Meetup token for analyzing this kind of repositories',
                                 'redirect': meetup_url_oauth},
                                status=401)
        return manage_add_meetup_repo(dash, data)

    else:
        return JsonResponse({'status': 'error', 'message': 'Backend not found'},
                            status=400)


def manage_add_gh_repo(dash, data, analyze_commits, analyze_issues_prs):
    """
    Add a repository or a user in a dashboard
    :param dash: Dashboard object for adding
    :param data: Dictionary with the user or the repository to be added. Format: {'user': 'xxx', 'repository': 'yyy'}
    :param analyze_commits: Analyze commits from the repositories
    :param analyze_issues_prs: Analyze issues and pull requests from the repositories
    :return:
    """
    if data['user'] and not data['repository']:
        gh_sync = GitHubSync(dash.creator.githubuser.token.key)
        try:
            git_list, github_list = gh_sync.get_repo(data['user'], False)
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': 'Error from GitHub API. ' + str(e)},
                                status=404)
        if analyze_issues_prs:
            for url in github_list:
                repo = add_to_dashboard(dash, 'github', url)
                start_task(repo, dash.creator.githubuser.token)
        if analyze_commits:
            for url in git_list:
                repo = add_to_dashboard(dash, 'git', url)
                start_task(repo, None)
    elif data['user'] and data['repository']:
        if analyze_issues_prs:
            url_gh = "https://github.com/{}/{}".format(data['user'], data['repository'])
            repo_gh = add_to_dashboard(dash, 'github', url_gh)
            start_task(repo_gh, dash.creator.githubuser.token)
        if analyze_commits:
            url_git = "https://github.com/{}/{}.git".format(data['user'], data['repository'])
            repo_git = add_to_dashboard(dash, 'git', url_git)
            start_task(repo_git, None)
    else:
        return JsonResponse({'status': 'error', 'message': 'Invalid data posted, something is missing'},
                            status=401)

    es_users = ESUser.objects.filter(dashboard=dash)
    update_role_dashboard(es_users.first().role, dash)

    return JsonResponse({'status': 'ok'})


def manage_add_gl_repo(dash, data, analyze_commits, analyze_issues_mrs):
    """
    Add a repository or a user in a dashboard
    :param dash: Dashboard object for adding
    :param data: Dictionary with the user or the repository to be added. Format: {'user': 'xxx', 'repository': 'yyy'}
    :param analyze_commits: Analyze commits from the repositories
    :param analyze_issues_mrs: Analyze issues and merge requests from the repositories
    :return:
    """
    if data['user'] and not data['repository']:
        try:
            gitlab_list, git_list = get_gl_repos(data['user'], dash.creator.gitlabuser.token.key)
        except Exception as e:
            logging.warning("Error for Gitlab owner {}: {}".format(data['user'], e))
            return JsonResponse({'status': 'error', 'message': 'Error from GitLab API. Does that user exist?'},
                                status=404)
        if analyze_issues_mrs:
            for url in gitlab_list:
                repo = add_to_dashboard(dash, 'gitlab', url)
                start_task(repo, dash.creator.gitlabuser.token)
        if analyze_commits:
            for url in git_list:
                repo = add_to_dashboard(dash, 'git', url)
                start_task(repo, None)
    elif data['user'] and data['repository']:
        if analyze_issues_mrs:
            url_gl = 'https://gitlab.com/{}/{}'.format(data['user'], data['repository'])
            repo_gl = add_to_dashboard(dash, 'gitlab', url_gl)
            start_task(repo_gl, dash.creator.gitlabuser.token)
        if analyze_commits:
            url_git = 'https://gitlab.com/{}/{}.git'.format(data['user'], data['repository'])
            repo_git = add_to_dashboard(dash, 'git', url_git)
            start_task(repo_git, None)
    else:
        return JsonResponse({'status': 'error', 'message': 'Invalid data posted, something is missing'},
                            status=401)

    es_users = ESUser.objects.filter(dashboard=dash)
    update_role_dashboard(es_users.first().role, dash)
    return JsonResponse({'status': 'ok'})


def manage_add_meetup_repo(dash, data):
    """
    Add a repository or a user in a dashboard
    :param dash: Dashboard object for adding
    :param data: Dictionary with the group to be added. Format: {'group': 'xxx'}
    :return:
    """
    if data['group']:
        r = requests.get('https://api.meetup.com/{}'.format(data['group']),
                         headers={'Authorization': 'bearer {}'.format(dash.creator.meetupuser.token.key)})
        group_info = r.json()
        if 'errors' in group_info:
            error_msg = group_info['errors'][0]['message']
            return JsonResponse({'status': "error", 'message': 'Error from Meetup API. {}'.format(error_msg)},
                                status=404)

        repo = add_to_dashboard(dash, 'meetup', data['group'])
        start_task(repo, dash.creator.meetupuser.token)

        es_users = ESUser.objects.filter(dashboard=dash)
        update_role_dashboard(es_users.first().role, dash)

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
    - Meetup group: "https://www.backend.com/one-group/"
    backend: Could be github, gitlab or meetup for git is always the URL
    :return:
    """
    gh_user_regex = '([a-zA-Z0-9](?:[a-zA-Z0-9]|-[a-zA-Z0-9]){1,38})'
    gh_repo_regex = '([a-zA-Z0-9\.\-\_]{1,100})'
    gl_user_regex = '([a-zA-Z0-9_\.][a-zA-Z0-9_\-\.]{1,200}[a-zA-Z0-9_\-]|[a-zA-Z0-9_])'
    gl_repo_regex = '([a-zA-Z0-9_\.][a-zA-Z0-9_\-\.]*[a-zA-Z0-9_\-\.])'
    meetup_group_regex = '([a-zA-Z0-9\-]{6,70})'
    language_code = '(?:/[a-zA-Z0-9\-]{2,5})?'
    data_guess = data_guess.strip()
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
    elif backend == 'meetup':
        re_url_group = re.match('^https?://www\.meetup\.com{}/{}/?'.format(language_code, meetup_group_regex), data_guess)
        if re_url_group:
            return {'group': re_url_group.groups()[0]}
        re_group = re.match('^{}$'.format(meetup_group_regex), data_guess)
        if re_group:
            return {'group': re_group.groups()[0]}
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
        return JsonResponse({'status': 'error', 'message': 'You are not authenticated',
                             'redirect': '/login?next=/dashboard/' + str(dash_id)}, status=401)

    if request.user != dash.creator and not request.user.is_superuser:
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

    dashboards = Dashboard.objects.filter(creator=dash.creator)
    for tmp_dash in dashboards:
        if tmp_dash.name == name:
            return JsonResponse({'status': 'Duplicate name', 'message': 'You have the same name in another Dashboard'},
                                status=400)
    old_name = dash.name
    dash.name = name
    dash.save()

    return JsonResponse({'status': 'Ok', 'message': 'Name updated from "{}" to "{}"'.format(old_name, name)})


def start_task(repo, token):
    """
    Start a new task for the given repository. If the repository has been analyzed,
    it will be refreshed
    :param repo: Repository object to analyze
    :param token: Token used for the analysis
    :return:
    """
    if not Task.objects.filter(repository=repo, tokens=token).first():
        CompletedTask.objects.filter(repository=repo, old=False).update(old=True)
        task = Task.objects.filter(repository=repo).first()
        if not task:
            file_log = '{}/repo_{}.log'.format(DASHBOARD_LOGS, repo.id)
            task = Task(repository=repo, log_file=file_log)
            task.save()
        if token:
            task.tokens.add(token)

        return True
    return False


def request_new_dashboard(request):
    """
    Create a new dashboard
    Redirect to the edit page for the dashboard
    """
    context = create_context(request)

    if request.method != 'POST':
        context['title'] = "Method Not Allowed"
        context['description'] = "Only POST methods allowed"
        return render(request, 'error.html', status=405,
                      context=context)

    if not request.user.is_authenticated:
        # Create a user
        dj_name = generate_random_uuid(length=96)
        dj_user = User.objects.create_user(username=dj_name, first_name="Anonymous")
        dj_user.set_unusable_password()
        dj_user.save()
        # Annotate as anonymous
        anonym_user = AnonymousUser(user=dj_user)
        anonym_user.save()
        # Log in
        login(request, dj_user)

    dash = Dashboard.objects.create(name=generate_random_uuid(length=12), creator=request.user)
    dash.name = "Project {}".format(dash.id)
    dash.save()

    create_kibana_users(dash)
    # TODO: If something is wrong delete the dashboard
    return HttpResponseRedirect('/dashboard/{}'.format(dash.id))


def create_kibana_users(dashboard):
    """
    Create ES users (public and private), a role and Role mapping
    :param dashboard: dashboard related to the users created
    :return:
    """
    private_username = "dashboard{}".format(dashboard.id)
    private_password = generate_random_uuid(length=32, delimiter='')
    pub_username = "publicdashboard{}".format(dashboard.id)
    pub_password = generate_random_uuid(length=32, delimiter='')
    role_name = "roledashboard{}".format(dashboard.id)

    odfe_api = OpendistroApi(ES_IN_URL, ES_ADMIN_PSW)
    odfe_api.create_user(private_username, private_password)
    odfe_api.create_user(pub_username, pub_password)
    odfe_api.put_role(role_name)
    odfe_api.create_mapping([private_username, pub_username], role_name)

    private_es_user = ESUser(name=private_username, password=private_password,
                             role=role_name, dashboard=dashboard, private=True)
    private_es_user.save()

    public_es_user = ESUser(name=pub_username, password=pub_password,
                            role=role_name, dashboard=dashboard, private=False)
    public_es_user.save()


def add_to_dashboard(dash, backend, url):
    """
    Add a repository to a dashboard
    :param dash: Dashboard row from db
    :param url: url for the analysis
    :param backend: Identity used like github, gitlab or meetup. See models.py for more details
    :return: Repository created
    """
    repo_obj = Repository.objects.filter(url=url, backend=backend).first()
    if not repo_obj:
        repo_obj = Repository(url=url, backend=backend)
        repo_obj.save()
    repo_obj.dashboards.add(dash)
    return repo_obj


def update_role_dashboard(role_name, dashboard):
    """
    Update the role with the current state of a dashboard
    Include read permission for .kibana
    Include read/write permissions for private .kibana

    :param role_name: name of the role
    :param dashboard: dashboard to be updated with the role
    :return:
    """
    repositories = Repository.objects.filter(dashboards=dashboard)

    permissions = {
        "index_permissions": [],
        "cluster_permissions": [],
        "tenant_permissions": []
    }

    for index in BACKEND_INDICES:
        repos_index = repositories.filter(backend=index['backend'])
        url_list = [repo.url for repo in repos_index]

        if len(url_list) == 0:
            # Include permissions to the repository '0' to avoid errors in visualizations
            url_list = ["0"]

        dls = {
            'terms': {
                index['url_field']: url_list
            }
        }
        str_dls = str(dls).replace("'", "\"")

        index_permissions = {
            'index_patterns': [index['name']],
            'dls': str_dls,
            'allowed_actions': [
                'read'
            ]
        }
        permissions["index_permissions"].append(index_permissions)

    kibana_permissions = {
        'index_patterns': ['?kibana'],
        'allowed_actions': [
            'read'
        ]
    }
    permissions["index_permissions"].append(kibana_permissions)

    private_kibana_permissions = {
        'index_patterns': ['?kibana_*_${user_name}'],
        'allowed_actions': [
            'read', 'delete', 'manage', 'index'
        ]
    }
    permissions["index_permissions"].append(private_kibana_permissions)

    global_tenant_permissions = {
        "tenant_patterns": [
            "global_tenant"
        ],
        "allowed_actions": [
            "kibana_all_read"
        ]
    }
    permissions["tenant_permissions"].append(global_tenant_permissions)

    odfe_api = OpendistroApi(ES_IN_URL, ES_ADMIN_PSW)
    odfe_api.put_role(role_name, permissions)


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


def get_dashboard_summary(dash_id):
    """
    Get a summary about the repositories in a dashboard
    :param dash_id: id of the dashboard
    :return:
    """
    summary = {
        'total': 0,
        'status': {}
    }

    repos = Repository.objects.filter(dashboards=dash_id)

    summary['total'] = CompletedTask.objects.filter(repository__in=repos, old=False).count() + \
                       Task.objects.filter(repository__in=repos).count()
    summary['status']['completed'] = CompletedTask.objects.filter(repository__in=repos,
                                                                  status="COMPLETED",
                                                                  old=False).count()
    summary['status']['pending'] = Task.objects.filter(repository__in=repos,
                                                       worker_id="").count()
    summary['status']['running'] = Task.objects.filter(repository__in=repos).exclude(worker_id="").count()
    summary['status']['error'] = CompletedTask.objects.filter(repository__in=repos,
                                                              status="ERROR",
                                                              old=False).count()

    return summary


def request_show_dashboard(request, dash_id):
    """
    View for a dashboard. It can be editable if the user is authenticated and is the creator
    :param request:
    :param dash_id:
    :return:
    """
    context = create_context(request)

    if request.method != 'GET':
        context['title'] = "Method Not Allowed"
        context['description'] = "Only GET methods allowed"
        return render(request, 'error.html', status=405,
                      context=context)

    dash = Dashboard.objects.filter(id=dash_id).first()
    if not dash:
        context['title'] = "Dashboard not found"
        context['description'] = "This dashboard was not found in this server"
        return render(request, 'error.html', status=405,
                      context=context)

    # CREATE RESPONSE
    # Information for the dashboard
    if dash:
        context['dashboard'] = dash
        context['repositories'] = Repository.objects.filter(dashboards__id=dash_id).order_by('-id')
        public_esuser = ESUser.objects.filter(dashboard=dash, private=False).first()
        if not public_esuser:
            context['title'] = "Error with public dashboards"
            context['description'] = "Maybe the data is not migrated. Please open an issue"
            return render(request, 'error.html', status=405,
                          context=context)
        jwt_key = get_kibana_jwt(public_esuser.name, public_esuser.role)
        context['public_link'] = "{}/?jwtToken={}&security_tenant=global".format(KIB_OUT_URL, jwt_key)

    context['editable'] = request.user.is_authenticated and request.user == dash.creator or request.user.is_superuser
    context['dash_id'] = dash_id

    return render(request, 'dashboard.html', context=context)


def request_delete_dashboard(request, dash_id):
    """
    Delete the project specified by the user
    """
    context = create_context(request)

    if request.method != 'POST':
        context['title'] = "Not allowed"
        context['description'] = "Method not allowed for this path"
        return render(request, 'error.html', status=405,
                      context=context)

    dash = Dashboard.objects.filter(id=dash_id).first()
    if not dash:
        context['title'] = "Project not found"
        context['description'] = "This project was not found in this server"
        return render(request, 'error.html', status=405,
                      context=context)

    owner = request.user.is_authenticated and request.user == dash.creator
    if not owner and not request.user.is_superuser:
        context['title'] = "Not allowed"
        context['description'] = "You are not allowed to delete this project."
        return render(request, 'error.html', status=400,
                      context=context)

    # Remove tasks in a transaction atomic
    with transaction.atomic():
        user_tokens = Token.objects.filter(user=dash.creator)
        tasks = Task.objects.filter(repository__in=dash.repository_set.all(), tokens__user=dash.creator)
        for task in tasks:
            task.tokens.remove(*user_tokens)

        remove_tasks_no_token()

    es_users = ESUser.objects.filter(dashboard=dash)
    odfe_api = OpendistroApi(ES_IN_URL, ES_ADMIN_PSW)
    for esuser in es_users:
        odfe_api.delete_user(esuser.name)
    dash.delete()
    return HttpResponseRedirect(reverse('projectspage'))


def remove_tasks_no_token():
    """
    Remove the tasks with no token (different from git) and then upgrade the completed tasks
    with the new old value
    """
    tasks = Task.objects.annotate(
        num_tokens=Count('tokens')
    ).filter(
        num_tokens=0
    ).exclude(
        repository__backend='git'
    )
    for task in tasks:
        CompletedTask.objects.filter(repository=task.repository).order_by('-completed').update(old=False)
        task.delete()


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

    if request.method != 'GET':
        return JsonResponse({'status': 'error', 'message': 'Only GET method allowed'}, status=405)

    owner = request.user.is_authenticated and request.user == dash.creator

    if owner or request.user.is_superuser:
        es_user = ESUser.objects.filter(dashboard=dash, private=True).first()
    else:
        es_user = ESUser.objects.filter(dashboard=dash, private=False).first()

    jwt_key = get_kibana_jwt(es_user.name, es_user.role)

    url = "{}/?jwtToken={}&security_tenant=global".format(KIB_OUT_URL, jwt_key)

    return HttpResponseRedirect(url)


def request_public_kibana(request, dash_id):
    """
    Redirect to Kibana
    :param request:
    :param dash_id:
    :return:
    """
    dash = Dashboard.objects.filter(id=dash_id).first()
    if not dash:
        return JsonResponse({'status': 'error', 'message': 'Dashboard not found'}, status=404)

    if request.method != 'GET':
        return JsonResponse({'status': 'error', 'message': 'Only GET method allowed'}, status=405)

    es_user = ESUser.objects.filter(dashboard=dash, private=False).first()

    jwt_key = get_kibana_jwt(es_user.name, es_user.role)

    url = "{}/?jwtToken={}&security_tenant=global".format(KIB_OUT_URL, jwt_key)

    return HttpResponseRedirect(url)


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
            token = Token.objects.filter(backend=identity, user=request.user).first()
            tasks = Task.objects.filter(tokens=token)
            for task in tasks:
                if len(task.tokens.all()) == 1 and not task.worker_id:
                    task.delete()
            request.user.githubuser.delete()
            token.delete()
        return JsonResponse({'status': 'ok'})

    elif identity == 'gitlab':
        if hasattr(request.user, 'gitlabuser'):
            token = Token.objects.filter(backend=identity, user=request.user).first()
            tasks = Task.objects.filter(tokens=token)
            for task in tasks:
                if len(task.tokens.all()) == 1 and not task.worker_id:
                    task.delete()
            request.user.gitlabuser.delete()
            token.delete()
        return JsonResponse({'status': 'ok'})

    elif identity == 'meetup':
        if hasattr(request.user, 'meetupuser'):
            token = Token.objects.filter(backend=identity, user=request.user).first()
            tasks = Task.objects.filter(tokens=token)
            for task in tasks:
                if len(task.tokens.all()) == 1 and not task.worker_id:
                    task.delete()
            request.user.meetupuser.delete()
            token.delete()
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
    context['meetup_uri_identity'] = MEETUP_URI_IDENTITY
    context['meetup_client_id'] = MEETUP_CLIENT_ID
    context['meetup_uri_redirect'] = "https://{}{}".format(request.get_host(), MEETUP_REDIRECT_PATH)

    # Information for the photo and the profile
    context['authenticated'] = request.user.is_authenticated
    if request.user.is_authenticated:
        context['auth_user_username'] = request.user.first_name
        if hasattr(request.user, 'githubuser'):
            context['photo_user'] = request.user.githubuser.photo
        elif hasattr(request.user, 'gitlabuser'):
            context['photo_user'] = request.user.gitlabuser.photo
        elif hasattr(request.user, 'meetupuser'):
            context['photo_user'] = request.user.meetupuser.photo
        else:
            context['photo_user'] = '/static/img/profile-default.png'

    # Information about the accounts connected
    context['github_enabled'] = hasattr(request.user, 'githubuser')
    context['gitlab_enabled'] = hasattr(request.user, 'gitlabuser')
    context['meetup_enabled'] = hasattr(request.user, 'meetupuser')

    # Information about Hatstall
    if HATSTALL_ENABLED:
        context['hatstall_url'] = HATSTALL_URL

    # Google Analytics
    if GOOGLE_ANALYTICS_ID:
        context['google_analytics_id'] = GOOGLE_ANALYTICS_ID

    return context


def repo_status(request, repo_id):
    context = create_context(request)
    if request.method != 'GET':
        context['title'] = "Method Not Allowed"
        context['description'] = "Only GET methods allowed"
        return render(request, 'error.html', status=405,
                      context=context)
    repo = Repository.objects.filter(id=repo_id).first()
    if not repo:
        return JsonResponse({'status': 'UNKNOWN'})
    return JsonResponse({'status': get_repo_status(repo)})


def request_dash_info(request, dash_id):
    info = get_dashboard_info(dash_id)
    return JsonResponse(info)


def request_dash_summary(request, dash_id):
    summary = get_dashboard_summary(dash_id)
    return JsonResponse(summary)


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


def get_repo_status(repo):
    """
    Check if there is a task associated or it has been completed
    :param repo: Repository object from the database
    :return: status (PENDING, RUNNING, COMPLETED)
    """
    task_repo = Task.objects.filter(repository=repo).first()
    if task_repo and task_repo.worker_id:
        return 'RUNNING'
    elif task_repo:
        return 'PENDING'
    c_task = CompletedTask.objects.filter(repository=repo).order_by('completed').last()
    if c_task:
        return c_task.status
    else:
        return 'UNKNOWN'


def get_gl_repos(owner, token):
    """
    Get all the repositories from a owner or a group
    Limited to 5 seconds
    :param owner: Group or user name
    :param token: Token for gitlab authentication. Must be oauth
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

        gl_urls_sg, git_urls_sg = get_urls_subgroups(owner, init_time)
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
        git_urls.append(project['http_url_to_repo'])
        gitlab_urls.append(project['web_url'])

    return gitlab_urls, git_urls


def get_urls_subgroups(group, init_time=time.time()):
    """
    Get repositories from subgroups
    Limited to 6 seconds
    NOTE: Auth token doesn't work with subgroups, no token required here (last update: 07-2019)
    :param group:
    :param init_time: The time it started
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
                main_group = project['path_with_namespace'].split('/')[0]
                subgroup = '%2F'.join(project['path_with_namespace'].split('/')[1:])
                gitlab_urls.append('https://gitlab.com/{}/{}'.format(main_group, subgroup))
                git_urls.append(project['http_url_to_repo'])
        gl_urls_sub, git_urls_sub = get_urls_subgroups(path, init_time)
        gitlab_urls += gl_urls_sub
        git_urls += git_urls_sub
        logging.error("Elapsed: {}".format(time.time()-init_time))
        if time.time() > init_time + 6:
            return gitlab_urls, git_urls

    return gitlab_urls, git_urls


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


def admin_page(request):
    """
    View for the administration page to show an overview of each dashboard
    :param request:
    :return:
    """
    context = create_context(request)

    if not request.user.is_authenticated or not request.user.is_superuser:
        context['title'] = "User Not Allowed"
        context['description'] = "Only Admin users allowed"
        return render(request, 'error.html', status=403,
                      context=context)
    if request.method != 'GET':
        context['title'] = "Method Not Allowed"
        context['description'] = "Only GET methods allowed"
        return render(request, 'error.html', status=405,
                      context=context)

    dashboards = Dashboard.objects.all()
    if dashboards:
        context['dashboards'] = []

        for dash in dashboards:
            dashboard = dict()
            dashboard['dashboard'] = dash
            repos = Repository.objects.filter(dashboards=dash)
            # Tasks
            dashboard['tasks_count'] = CompletedTask.objects.filter(repository__in=repos,
                                                                    old=False).count() + \
                                       Task.objects.filter(repository__in=repos).count()
            dashboard['completed_tasks_count'] = CompletedTask.objects.filter(repository__in=repos,
                                                                              status="COMPLETED",
                                                                              old=False).count()
            dashboard['running_tasks_count'] = Task.objects.filter(repository__in=repos).exclude(worker_id="").count()
            dashboard['pending_tasks_count'] = Task.objects.filter(repository__in=repos,
                                                                   worker_id="").count()
            dashboard['error_tasks_count'] = CompletedTask.objects.filter(repository__in=repos,
                                                                          status="ERROR",
                                                                          old=False).count()
            # Data sources (Formerly Repositories)
            dashboard['repos_count'] = repos.count()
            dashboard['repos_git_count'] = repos.filter(backend="git").count()
            dashboard['repos_github_count'] = repos.filter(backend="github").count()
            dashboard['repos_gitlab_count'] = repos.filter(backend="gitlab").count()
            dashboard['repos_meetup_count'] = repos.filter(backend="meetup").count()

            context['dashboards'].append(dashboard)

    # Total Dashboards
    context['dash_count'] = Dashboard.objects.count()
    # Total Tasks
    context['tasks_count'] = Task.objects.count() + CompletedTask.objects.filter(old=False).count()
    context['completed_tasks_count'] = CompletedTask.objects.filter(status="COMPLETED", old=False).count()
    context['running_tasks_count'] = Task.objects.exclude(worker_id="").count()
    context['pending_tasks_count'] = Task.objects.filter(worker_id="").count()
    context['error_tasks_count'] = CompletedTask.objects.filter(status="ERROR", old=False).count()
    # Total Data sources (Formerly Repositories)
    context['repos_count'] = Repository.objects.exclude(dashboards=None).count()
    context['repos_git_count'] = Repository.objects.exclude(dashboards=None).filter(backend="git").count()
    context['repos_github_count'] = Repository.objects.exclude(dashboards=None).filter(backend="github").count()
    context['repos_gitlab_count'] = Repository.objects.exclude(dashboards=None).filter(backend="gitlab").count()
    context['repos_meetup_count'] = Repository.objects.exclude(dashboards=None).filter(backend="meetup").count()

    return render(request, 'admin.html', context=context)
