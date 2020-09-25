from django.shortcuts import render
from django.http import HttpResponseRedirect, JsonResponse
from django.contrib.auth import login, logout
from django.contrib.auth.models import User
from django.urls import reverse
from django.db import transaction
from django.db.models import Count, Q
from django.views.decorators.http import require_http_methods
from CauldronApp.pages import Pages
from CauldronApp import kibana_objects, utils
from CauldronApp.project_metrics import metrics

import os
import re
import logging
import requests
from github import Github
from random import choice
from string import ascii_lowercase, digits
from urllib.parse import urlencode
import time
import datetime
from dateutil.relativedelta import relativedelta

from Cauldron2.settings import ES_IN_HOST, ES_IN_PORT, ES_IN_PROTO, ES_ADMIN_PASSWORD, \
                               KIB_IN_HOST, KIB_IN_PORT, KIB_IN_PROTO, KIB_OUT_URL, \
                               KIB_PATH, HATSTALL_ENABLED, GOOGLE_ANALYTICS_ID
from Cauldron2 import settings

from CauldronApp.models import GithubUser, GitlabUser, MeetupUser, Dashboard, Repository, Task, \
                               CompletedTask, AnonymousUser, ProjectRole, Token, UserWorkspace

from CauldronApp.opendistro_utils import OpendistroApi
from CauldronApp.oauth.github import GitHubOAuth
from CauldronApp.oauth.gitlab import GitLabOAuth
from CauldronApp.oauth.meetup import MeetupOAuth

from .project_metrics.metrics import get_compare_metrics, get_compare_charts

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

DASHBOARD_LOGS = '/dashboard_logs'

BACKEND_INDICES = [
    # {
    #     "name": "git_aoc_enriched_index",
    #     "backend": "git",
    #     "url_field": "repository"
    # },
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
    # {
    #     "name": "github_pull_enrich_index",
    #     "backend": "github",
    #     "url_field": "repository"
    # },
    {
        "name": "github_repo_enrich_index",
        "backend": "github",
        "url_field": "origin"
    },
    {
        "name": "github2_enrich_index",
        "backend": "github",
        "url_field": "repository"
    },
    # {
    #     "name": "github2_pull_enrich_index",
    #     "backend": "github",
    #     "url_field": "repository"
    # },
    {
        "name": "gitlab_enriched_index",
        "backend": "gitlab",
        "url_field": "repository"
    },
    {
        "name": "gitlab_mrs_enriched_index",
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

logger = logging.getLogger(__name__)


def homepage(request):
    # If user is authenticated, homepage is My projects page
    if request.user.is_authenticated:
        return request_user_projects(request)

    context = create_context(request)

    return render(request, 'cauldronapp/index.html', context=context)


def request_user_projects(request):
    context = create_context(request)
    if not request.user.is_authenticated:
        context['title'] = "You are not logged in"
        context['description'] = "You need to login or create a new project to continue"
        return render(request, 'cauldronapp/error.html', status=400, context=context)
    else:
        projects = Dashboard.objects.filter(creator=request.user)
        projects_info = list()

        search = request.GET.get('search')
        if search is not None:
            projects = projects.filter(name__icontains=search)

        p = Pages(projects, 9)
        page_number = request.GET.get('page', 1)
        page_obj = p.pages.get_page(page_number)
        context['page_obj'] = page_obj
        context['pages_to_show'] = p.pages_to_show(page_obj.number)

        for project in page_obj.object_list:
            repositories = Repository.objects.filter(dashboards=project.pk)
            n_github = repositories.filter(backend='github').count()
            n_git = repositories.filter(backend='git').count()
            n_gitlab = repositories.filter(backend='gitlab').count()
            n_meetup = repositories.filter(backend='meetup').count()
            n_completed = CompletedTask.objects.filter(repository__in=repositories, status='COMPLETED', old=False).count()
            n_errors = CompletedTask.objects.filter(repository__in=repositories, status='ERROR', old=False).count()
            n_pending = Task.objects.filter(repository__in=repositories).count()
            projects_info.append({
                'project': project,
                'completed': n_completed,
                'errors': n_errors,
                'pending': n_pending,
                'github': n_github,
                'git': n_git,
                'gitlab': n_gitlab,
                'meetup': n_meetup,
                'total': n_completed + n_errors + n_pending
            })
        context['projects_info'] = projects_info
    return render(request, 'cauldronapp/projects.html', context=context)


# TODO: Add state
def request_github_oauth(request):
    code = request.GET.get('code', None)
    if not code:
        return custom_404(request, "Code not found in the GitHub callback")

    github = GitHubOAuth(settings.GH_CLIENT_ID, settings.GH_CLIENT_SECRET)
    error = github.authenticate(code)
    if error:
        return custom_500(request, error)
    oauth_user = github.user_data()

    is_admin = oauth_user.username in settings.CAULDRON_ADMINS['GITHUB']

    # Save the state of the session
    data_add = request.session.pop('add_repo', None)
    last_page = request.session.pop('last_page', None)

    merged = authenticate_user(request, GithubUser, oauth_user, is_admin)

    if data_add:
        dash = Dashboard.objects.filter(id=data_add['dash_id']).first()
        # Only GitHub, is the new account added
        if data_add['backend'] == 'github':
            commits = data_add['commits']
            issues = data_add['issues']
            forks = data_add['forks']
            manage_add_gh_repo(dash, data_add['data'], commits, issues, forks)

    if merged:
        request.session['alert_notification'] = {'title': 'Account merged',
                                                 'message': f"You already had a Cauldron user with this GitHub account."
                                                            f" We have proceeded to merge all the projects and "
                                                            f"visualization in you current account so that you do not "
                                                            f"loose anything"}

    if last_page:
        return HttpResponseRedirect(last_page)

    return HttpResponseRedirect(reverse('homepage'))


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
    merge_workspaces(user_origin, user_dest)
    merge_admins(user_origin, user_dest)


def merge_admins(old_user, new_user):
    """
    Convert the new user to admin if the old one was an admin
    :param old_user: User to delete
    :param new_user: User to keep
    :return:
    """
    new_user.is_staff = new_user.is_staff or old_user.is_staff
    new_user.is_superuser = new_user.is_superuser or old_user.is_superuser
    new_user.save()


def merge_workspaces(old_user, new_user):
    """
    Try to copy all the visualizations from one tenant to the other one
    :param old_user:
    :param new_user:
    :return:
    """
    if not hasattr(old_user, 'userworkspace'):
        return
    if not hasattr(new_user, 'userworkspace'):
        create_workspace(new_user)

    obj = kibana_objects.export_all_objects(KIB_IN_URL, ES_ADMIN_PASSWORD, old_user.userworkspace.tenant_name)
    kibana_objects.import_object(KIB_IN_URL, ES_ADMIN_PASSWORD, obj, new_user.userworkspace.tenant_name)


# TODO: Add state
def request_gitlab_oauth(request):
    code = request.GET.get('code', None)
    if not code:
        return custom_404(request, "Code not found in the GitLab callback")
    redirect_uri = "https://{}{}".format(request.get_host(), GitLabOAuth.REDIRECT_PATH)
    gitlab = GitLabOAuth(settings.GL_CLIENT_ID, settings.GL_CLIENT_SECRET, redirect_uri)
    error = gitlab.authenticate(code)
    if error:
        return custom_500(request, error)
    oauth_user = gitlab.user_data()

    is_admin = oauth_user.username in settings.CAULDRON_ADMINS['GITLAB']

    # Save the state of the session
    data_add = request.session.pop('add_repo', None)
    last_page = request.session.pop('last_page', None)

    merged = authenticate_user(request, GitlabUser, oauth_user, is_admin)

    if data_add:
        dash = Dashboard.objects.filter(id=data_add['dash_id']).first()
        # Only GitLab, is the new account added
        if data_add['backend'] == 'gitlab':
            commits = data_add['commits']
            issues = data_add['issues']
            forks = data_add['forks']
            manage_add_gl_repo(dash, data_add['data'], commits, issues, forks)

    if merged:
        request.session['alert_notification'] = {'title': 'Account merged',
                                                 'message': f"You already had a Cauldron user with this GitLab account."
                                                            f" We have proceeded to merge all the projects and "
                                                            f"visualization in you current account so that you do not "
                                                            f"loose anything"}

    if last_page:
        return HttpResponseRedirect(last_page)

    return HttpResponseRedirect(reverse('homepage'))


# TODO: Add state
def request_meetup_oauth(request):
    error = request.GET.get('error', None)
    if error:
        return custom_404(request, f"Meetup callback error. {error}")
    code = request.GET.get('code', None)
    if not code:
        return custom_404(request, "Code not found in the Meetup callback")
    redirect_uri = "https://{}{}".format(request.get_host(), MeetupOAuth.REDIRECT_PATH)
    meetup = MeetupOAuth(settings.MEETUP_CLIENT_ID, settings.MEETUP_CLIENT_SECRET, redirect_uri)
    error = meetup.authenticate(code)
    if error:
        return custom_500(request, error)
    oauth_user = meetup.user_data()

    is_admin = oauth_user.username in settings.CAULDRON_ADMINS['MEETUP']

    # Save the state of the session
    data_add = request.session.pop('add_repo', None)
    last_page = request.session.pop('last_page', None)

    merged = authenticate_user(request, MeetupUser, oauth_user, is_admin)

    request.user.meetupuser.refresh_token = oauth_user.refresh_token
    request.user.meetupuser.save()

    if data_add:
        dash = Dashboard.objects.filter(id=data_add['dash_id']).first()
        if data_add['backend'] == 'meetup':
            manage_add_meetup_repo(dash, data_add['data'])

    if merged:
        request.session['alert_notification'] = {'title': 'Account merged',
                                                 'message': f"You already had a Cauldron user with this Meetup account."
                                                            f" We have proceeded to merge all the projects and "
                                                            f"visualization in you current account so that you do not "
                                                            f"loose anything"}

    if last_page:
        return HttpResponseRedirect(last_page)

    return HttpResponseRedirect(reverse('homepage'))


def authenticate_user(request, backend_model, oauth_user, is_admin=False):
    """
    Authenticate an oauth request and merge with existent accounts if needed
    :param request: request from login callback
    :param backend_model: GitlabUser, GithubUser, MeetupUser ...
    :param oauth_user: user information obtained from the backend
    :param is_admin: flag to indicate that the user to authenticate is an admin
    :return: boolean. The user has been merged
    """
    merged = False
    backend_entity = backend_model.objects.filter(username=oauth_user.username).first()
    backend_user = backend_entity.user if backend_entity else None

    if backend_user:
        if request.user.is_authenticated and backend_user != request.user:
            # Someone is authenticated, backend user exists and not are the same account
            merge_accounts(user_origin=request.user, user_dest=backend_user)
            request.user.delete()
            login(request, backend_user)
            merged = True
        else:
            # No one is authenticated and backend user exists
            login(request, backend_user)
        # Update the token
        backend_entity.token.key = oauth_user.token
        backend_entity.token.save()
    else:
        if request.user.is_authenticated:
            # Someone is authenticated and backend user doesn't exist
            # Check if is anonymous and delete anonymous tag
            anony_user = AnonymousUser.objects.filter(user=request.user).first()
            if anony_user:
                anony_user.delete()
                request.user.first_name = oauth_user.name
                request.user.save()

        else:
            # No one is authenticated and backend user doesn't exist
            # Create account
            dj_user = create_django_user(oauth_user.name)
            login(request, dj_user)

        # If it is an admin user, upgrade it
        if is_admin:
            upgrade_to_admin(request.user)

        # Create the token entry
        token = Token.objects.create(backend=backend_model.BACKEND_NAME, key=oauth_user.token, user=request.user)

        # Create the backend entity and associate with the account
        backend_model.objects.create(user=request.user, username=oauth_user.username,
                                     token=token, photo=oauth_user.photo)

    return merged


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


def upgrade_to_admin(user):
    """
    Upgrades a user to Cauldron Admin
    :user: user to be checked
    :return:
    """
    user.is_staff = True
    user.is_superuser = True
    user.save()


def request_logout(request):
    logout(request)
    return HttpResponseRedirect('/')


def generate_request_token_message(backend):
    return f'When you click "Go", you will be prompted by {backend} to grant ' \
           f'Cauldron some permissions to retrieve data on your behalf, so ' \
           f'that we can analyze the repositories you specify.<br> You can revoke ' \
           f'this permission whenever you may want, either in {backend} or in ' \
           f'Cauldron.<br> For details, see our <a href="{reverse("terms")}">Terms of service</a> ' \
           f'and <a href="{reverse("privacy")}">privacy</a> document'


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

    if action == 'delete':
        repo = Repository.objects.filter(id=data_in, backend=backend).first()
        if not repo:
            return JsonResponse({'status': 'error', 'message': 'Repository not found'},
                                status=404)
        repo.dashboards.remove(dash)
        update_role_dashboard(dash.projectrole.role, dash)
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
        start_task(repo=repo, token=token)
        return JsonResponse({'status': 'reanalyze'})

    elif action == 'reanalyze-all':
        repos = Repository.objects.filter(dashboards=dash_id)
        if not repos:
            return JsonResponse({'status': 'error', 'message': 'Repositories not found'},
                                status=404)
        for repo in repos:
            token = Token.objects.filter(user=dash.creator, backend=repo.backend).first()
            if token or repo.backend == 'git':
                start_task(repo=repo, token=token)
        return JsonResponse({'status': 'reanalyze',
                             'message': "Refreshing all the repositories"})

    # From here the action should be add
    if backend == 'git':
        # Remove the spaces to avoid errors
        data = data_in.strip()
        repo = add_to_dashboard(dash, backend, data)
        update_role_dashboard(dash.projectrole.role, dash)
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
        forks = 'forks' in request.POST
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
                                           'forks': forks,
                                           'issues': analyze_issues}
            request.session['last_page'] = '/dashboard/{}'.format(dash_id)
            params = urlencode({'client_id': settings.GH_CLIENT_ID})
            gh_url_oauth = "{}?{}".format(GitHubOAuth.AUTH_URL, params)
            return JsonResponse({'status': 'error',
                                 'message': generate_request_token_message("GitHub"),
                                 'redirect': gh_url_oauth},
                                status=401)
        return manage_add_gh_repo(dash, data, analyze_commits, analyze_issues, forks)

    elif backend == 'gitlab':
        analyze_commits = 'commits' in request.POST
        analyze_issues = 'issues' in request.POST
        forks = 'forks' in request.POST
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
                                           'forks': forks,
                                           'issues': analyze_issues}
            request.session['last_page'] = '/dashboard/{}'.format(dash_id)
            params = urlencode({'client_id': settings.GL_CLIENT_ID,
                                'response_type': 'code',
                                'redirect_uri': "https://{}{}".format(request.get_host(),
                                                                      GitLabOAuth.REDIRECT_PATH)})
            gl_url_oauth = "{}?{}".format(GitLabOAuth.AUTH_URL, params)
            return JsonResponse({'status': 'error',
                                 'message': generate_request_token_message("GitLab"),
                                 'redirect': gl_url_oauth},
                                status=401)
        return manage_add_gl_repo(dash, data, analyze_commits, analyze_issues, forks)

    elif backend == 'meetup':
        if not hasattr(dash.creator, 'meetupuser'):
            if request.user != dash.creator:
                return JsonResponse({'status': 'error',
                                     'message': 'Dashboard owner needs a Meetup token to'
                                                ' analyze this kind of repositories'},
                                    status=401)
            request.session['add_repo'] = {'data': data, 'backend': backend, 'dash_id': dash.id}
            request.session['last_page'] = '/dashboard/{}'.format(dash_id)
            params = urlencode({'client_id': settings.MEETUP_CLIENT_ID,
                                'response_type': 'code',
                                'redirect_uri': "https://{}{}".format(request.get_host(),
                                                                      MeetupOAuth.REDIRECT_PATH)})
            meetup_url_oauth = "{}?{}".format(MeetupOAuth.AUTH_URL, params)
            return JsonResponse({'status': 'error',
                                 'message': generate_request_token_message("Meetup"),
                                 'redirect': meetup_url_oauth},
                                status=401)
        return manage_add_meetup_repo(dash, data)

    else:
        return JsonResponse({'status': 'error', 'message': 'Backend not found'},
                            status=400)


def manage_add_gh_repo(dash, data, analyze_commits, analyze_issues_prs, forks=False):
    """
    Add a repository or a user in a dashboard
    :param dash: Dashboard object for adding
    :param data: Dictionary with the user or the repository to be added. Format: {'user': 'xxx', 'repository': 'yyy'}
    :param analyze_commits: Analyze commits from the repositories
    :param analyze_issues_prs: Analyze issues and pull requests from the repositories
    :param forks: Analyze forks
    :return:
    """
    if data['user'] and not data['repository']:
        github_repos, git_repos = [], []
        github = Github(dash.creator.githubuser.token.key)
        try:
            repositories = github.get_user(data['user']).get_repos()
            for repo_gh in repositories:
                if not repo_gh.fork or forks:
                    if analyze_issues_prs:
                        repo = add_to_dashboard(dash, 'github', repo_gh.html_url)
                        start_task(repo, dash.creator.githubuser.token)
                    if analyze_commits:
                        repo = add_to_dashboard(dash, 'git', repo_gh.clone_url)
                        start_task(repo, None)
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': 'Error from GitHub API. ' + str(e)},
                                status=404)
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

    update_role_dashboard(dash.projectrole.role, dash)

    return JsonResponse({'status': 'ok'})


def manage_add_gl_repo(dash, data, analyze_commits, analyze_issues_mrs, forks=False):
    """
    Add a repository or a user in a dashboard
    :param dash: Dashboard object for adding
    :param data: Dictionary with the user or the repository to be added. Format: {'user': 'xxx', 'repository': 'yyy'}
    :param analyze_commits: Analyze commits from the repositories
    :param analyze_issues_mrs: Analyze issues and merge requests from the repositories
    :param forks: include forks in the analysis
    :return:
    """
    if data['user'] and not data['repository']:
        try:
            gitlab_list, git_list = get_gl_repos(data['user'], dash.creator.gitlabuser.token.key, forks)
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
            repo_encoded = '%2F'.join(data['repository'].strip('/').split('/'))
            url_gl = 'https://gitlab.com/{}/{}'.format(data['user'], repo_encoded)
            repo_gl = add_to_dashboard(dash, 'gitlab', url_gl)
            start_task(repo_gl, dash.creator.gitlabuser.token)
        if analyze_commits:
            url_git = 'https://gitlab.com/{}/{}.git'.format(data['user'], data['repository'])
            repo_git = add_to_dashboard(dash, 'git', url_git)
            start_task(repo_git, None)
    else:
        return JsonResponse({'status': 'error', 'message': 'Invalid data posted, something is missing'},
                            status=401)

    update_role_dashboard(dash.projectrole.role, dash)
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

        update_role_dashboard(dash.projectrole.role, dash)

        return JsonResponse({'status': 'ok'})

    return JsonResponse({'status': 'error', 'message': 'Invalid data posted, something is missing'},
                        status=401)


def guess_data_backend(data_guess, backend):
    """
    Guess the following formats:
    - User: "user"
    - User/Repository: "user/repository"
    - Group/subgroup/repository: "group/subgroup/.../repository"
    - URL of user: "https://backend.com/user"
    - URL of repository: "https://backend.com/user/repository"
    - URL of repository group: "https://gitlab.com/group/subgroup/subgroup/repository"
    - Meetup group: "https://www.backend.com/one-group/"
    backend: Could be github, gitlab or meetup for git is always the URL
    :return:
    """
    gh_user_regex = '([a-zA-Z0-9](?:[a-zA-Z0-9]|-[a-zA-Z0-9]){1,38})'
    gh_repo_regex = '([a-zA-Z0-9\.\-\_]{1,100})'
    gl_user_regex = '([a-zA-Z0-9_\.][a-zA-Z0-9_\-\.]{1,200}[a-zA-Z0-9_\-]|[a-zA-Z0-9_])'
    gl_repo_regex = '((?:[a-zA-Z0-9_\.][a-zA-Z0-9_\-\.]*(?:\/)?)+)'
    meetup_group_regex = '([a-zA-Z0-9\-]{6,70})'
    language_code = '(?:\/[a-zA-Z0-9\-]{2,5})?'
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
        re_url_user = re.match('^https?:\/\/gitlab\.com\/{}\/?$'.format(gl_user_regex), data_guess)
        if re_url_user:
            return {'user': re_url_user.groups()[0], 'repository': None}
        re_url_repo = re.match('^https?:\/\/gitlab\.com\/{}\/{}(?:.git)?$'.format(gl_user_regex, gl_repo_regex), data_guess)
        if re_url_repo:
            return {'user': re_url_repo.groups()[0], 'repository': re_url_repo.groups()[1]}
        re_user_repo = re.match('{}/{}$'.format(gl_user_regex, gl_repo_regex), data_guess)
        if re_user_repo:
            return {'user': re_user_repo.groups()[0], 'repository': re_user_repo.groups()[1]}
    elif backend == 'meetup':
        re_url_group = re.match('^https?:\/\/www\.meetup\.com{}\/{}\/?'.format(language_code, meetup_group_regex), data_guess)
        if re_url_group:
            return {'group': re_url_group.groups()[0]}
        re_group = re.match('^{}$'.format(meetup_group_regex), data_guess)
        if re_group:
            return {'group': re_group.groups()[0]}
    return None


@require_http_methods(["POST"])
def request_rename_project(request, dash_id):
    """
    Update the name for a project
    :param request: Object from Django
    :param dash_id: ID for the project to change
    :return:
    """
    try:
        dash = Dashboard.objects.get(id=dash_id)
    except Dashboard.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': f"Project {dash_id} doesn't exist"},
                            status=404)

    if not request.user.is_authenticated and request.user != dash.creator and not request.user.is_superuser:
        return JsonResponse({'status': 'error', 'message': f'You cannot edit project {dash_id}, you are not the owner'},
                            status=400)

    name = request.POST.get('name', '')
    name = name.strip()

    if len(name) < 1 or len(name) > 32:
        return JsonResponse({'status': 'error', 'message': "The name doesn't fit the allowed length "},
                            status=400)

    if Dashboard.objects.filter(creator=dash.creator, name=name).exists():
        return JsonResponse({'status': 'Duplicated name', 'message': 'You have the same name in another Dashboard'},
                            status=400)

    dash.name = name
    dash.save()

    return JsonResponse({'status': 'Ok', 'message': 'Name updated successfully'})


def start_task(repo, token):
    """
    Start a new task for the given repository. If the repository has been analyzed,
    it will be refreshed
    :param repo: Repository object to analyze
    :param token: Token used for the analysis
    :return:
    """
    log_file = '{}/repo_{}.log'.format(DASHBOARD_LOGS, repo.id)
    task, created = Task.objects.get_or_create(repository=repo, defaults={'log_file': log_file})
    if created:
        CompletedTask.objects.filter(repository=repo, old=False).update(old=True)
    if token:
        task.tokens.add(token)


def request_new_dashboard(request):
    """
    Create a new dashboard
    Redirect to the edit page for the dashboard
    """
    context = create_context(request)

    if request.method != 'POST':
        context['title'] = "Method Not Allowed"
        context['description'] = "Only POST methods allowed"
        return render(request, 'cauldronapp/error.html', status=405,
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

    create_project_elastic_role(dash)
    # TODO: If something is wrong delete the dashboard
    return HttpResponseRedirect('/dashboard/{}'.format(dash.id))


def create_project_elastic_role(dashboard):
    """
    Create a Elastic Role and the mapping for a Backend Role for the project,
    :param dashboard:
    :return:
    """
    role = f"role_project_{dashboard.id}"
    backend_role = f"br_project_{dashboard.id}"

    odfe_api = OpendistroApi(ES_IN_URL, ES_ADMIN_PASSWORD)
    odfe_api.create_role(role)
    odfe_api.create_mapping(role, backend_roles=[backend_role])

    ProjectRole.objects.create(role=role, backend_role=backend_role, dashboard=dashboard)


def add_to_dashboard(dash, backend, url):
    """
    Add a repository to a dashboard
    :param dash: Dashboard row from db
    :param url: url for the analysis
    :param backend: Identity used like github, gitlab or meetup. See models.py for more details
    :return: Repository created
    """
    repo_obj, _ = Repository.objects.get_or_create(url=url, backend=backend)
    repo_obj.dashboards.add(dash)
    return repo_obj


def update_role_dashboard(role_name, dashboard):
    """
    Update the role with the current state of a dashboard
    Include read permission for .kibana

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
        repos_index = repositories.filter(backend=index['backend']).values('url')
        url_list = [repo['url'] for repo in repos_index]

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

    global_tenant_permissions = {
        "tenant_patterns": [
            "global_tenant"
        ],
        "allowed_actions": [
            "kibana_all_read"
        ]
    }
    permissions["tenant_permissions"].append(global_tenant_permissions)

    odfe_api = OpendistroApi(ES_IN_URL, ES_ADMIN_PASSWORD)
    odfe_api.create_role(role_name, permissions)


def get_dashboard_summary(dash_id):
    """
    Get a summary about the repositories in a dashboard
    :param dash_id: id of the dashboard
    :return:
    """
    summary = {
        'id': dash_id,
        'total': 0,
        'status': {},
        'repositories': {}
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

    for backend in Repository.BACKEND_CHOICES:
        summary['repositories'][backend] = repos.filter(backend=backend).count()

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
        return custom_405(request, request.method)

    try:
        dash = Dashboard.objects.get(pk=dash_id)
    except Dashboard.DoesNotExist:
        return custom_404(request, "The project requested was not found in this server")

    context['dashboard'] = dash

    if request.user.is_authenticated:
        context['projects_compare'] = request.user.dashboard_set.exclude(pk=dash.pk)

    repositories = dash.repository_set.all()

    context['repositories_count'] = repositories.count()
    context['render_table'] = False

    search = request.GET.get('search')
    if search is not None:
        repositories = repositories.filter(url__icontains=search)

    kind = request.GET.getlist('kind')
    if kind and set(kind).issubset(set(Repository.BACKEND_CHOICES)):
        repositories = repositories.filter(backend__in=kind)

    status = request.GET.getlist('status')
    if status and set(status).issubset(set(Repository.STATUS_CHOICES)):
        repositories = [obj for obj in repositories.all() if obj.status in status]

    if kind or status or search:
        context['render_table'] = True

    sort_by = request.GET.get('sort_by')
    if sort_by is not None and sort_by in Repository.SORT_CHOICES:
        reverse = False
        if sort_by[0] == '-':
            reverse = True
            sort_by = sort_by[1:]

        if sort_by == 'kind':
            repositories = sorted(repositories, key=lambda r: r.backend, reverse=reverse)
        elif sort_by == 'status':
            repositories = sorted(repositories, key=lambda r: r.status, reverse=reverse)
        elif sort_by == 'refresh':
            repositories = sorted(repositories, key=lambda r: r.last_refresh, reverse=not reverse)
        elif sort_by == 'duration':
            repositories = sorted(repositories, key=lambda r: r.duration, reverse=reverse)

    p = Pages(repositories, 10)
    page_number = request.GET.get('page', 1)
    page_obj = p.pages.get_page(page_number)
    context['page_obj'] = page_obj
    context['pages_to_show'] = p.pages_to_show(page_obj.number)

    summary = get_dashboard_summary(dash_id)
    context['total'] = summary['total']
    context['completed'] = summary['status']['completed']
    context['error'] = summary['status']['error']
    context['running'] = summary['status']['running']

    context['is_outdated'] = dash.is_outdated
    if context['is_outdated']:
        context['last_refresh'] = dash.last_refresh

    context['editable'] = request.user.is_authenticated and request.user == dash.creator or request.user.is_superuser

    return render(request, 'cauldronapp/dashboard.html', context=context)


def request_compare_projects(request):
    """
    View for the dashboards comparison.
    :param request:
    :return:
    """
    context = create_context(request)

    if request.method != 'GET':
        return custom_405(request, request.method)

    try:
        projects_id = list(map(int, request.GET.getlist('projects')))
    except ValueError:
        projects_id = []

    if projects_id:
        projects = Dashboard.objects.filter(id__in=projects_id)
    else:
        projects = Dashboard.objects.none()

    if projects.count() > 2:
        return custom_403(request)

    context['projects'] = projects

    if request.user.is_authenticated:
        context['user_projects'] = request.user.dashboard_set.all()

    if projects.filter(repository=None).count() > 0:
        context['message_error'] = "Some of the selected projects do not have repositories..."
        context['projects'] = Dashboard.objects.none()
    else:
        try:
            from_str = request.GET.get('from_date', '')
            from_date = datetime.datetime.strptime(from_str, '%Y-%m-%d')
        except ValueError:
            from_date = datetime.datetime.now() - relativedelta(years=1)
        try:
            to_str = request.GET.get('to_date', '')
            to_date = datetime.datetime.strptime(to_str, '%Y-%m-%d')
        except ValueError:
            to_date = datetime.datetime.now()

        context['metrics'] = get_compare_metrics(projects, from_date, to_date)
        context['charts'] = get_compare_charts(projects, from_date, to_date)

    return render(request, 'cauldronapp/projects_compare.html', context=context)


def request_project_metrics(request, dash_id):
    """Obtain the metrics related to a project for a category. By default overview"""
    if request.method != 'GET':
        return custom_405(request, request.method)

    category = request.GET.get('tab', 'overview')

    try:
        dashboard = Dashboard.objects.get(pk=dash_id)
    except Dashboard.DoesNotExist:
        return custom_404(request, "The project requested was not found in this server")

    try:
        from_str = request.GET.get('from', '')
        from_date = datetime.datetime.strptime(from_str, '%Y-%m-%d')
    except ValueError:
        from_date = datetime.datetime.now() - relativedelta(years=1)
    try:
        to_str = request.GET.get('to', '')
        to_date = datetime.datetime.strptime(to_str, '%Y-%m-%d')
    except ValueError:
        to_date = datetime.datetime.now()

    return JsonResponse(metrics.get_category_metrics(dashboard, category, from_date, to_date))


def delete_dashboard(dashboard):
    # Remove tasks in a transaction atomic
    with transaction.atomic():
        user_tokens = Token.objects.filter(user=dashboard.creator)
        tasks = Task.objects.filter(repository__in=dashboard.repository_set.all(), tokens__user=dashboard.creator)
        for task in tasks:
            task.tokens.remove(*user_tokens)

        remove_tasks_no_token()

    odfe_api = OpendistroApi(ES_IN_URL, ES_ADMIN_PASSWORD)
    odfe_api.delete_mapping(dashboard.projectrole.role)
    odfe_api.delete_role(dashboard.projectrole.role)
    dashboard.delete()


def delete_user(user):
    for dashboard in user.dashboard_set.all():
        delete_dashboard(dashboard)
    if hasattr(user, 'userworkspace'):
        remove_workspace(user)

    user.delete()


def request_delete_dashboard(request, dash_id):
    """
    Delete the project specified by the user
    """
    if request.method != 'POST':
        return custom_405(request, request.method)

    try:
        dash = Dashboard.objects.get(id=dash_id)
    except Dashboard.DoesNotExist:
        return custom_404(request, "The project requested was not found in this server")

    owner = request.user.is_authenticated and request.user == dash.creator
    if not owner and not request.user.is_superuser:
        return custom_403(request)

    delete_dashboard(dash)

    return JsonResponse({'status': 'Ok', 'id': dash_id, 'message': 'Dashboard deleted successfully'})


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


def request_workspace(request, dash_id):
    """
    Redirect to My workspace of the requested project or create it
    :param request:
    :param dash_id: ID of the project
    :return:
    """
    dash = Dashboard.objects.filter(id=dash_id).first()
    if not dash:
        return custom_404(request, "The project requested was not found in this server")

    is_owner = request.user.is_authenticated and request.user == dash.creator
    if not is_owner and not request.user.is_superuser:
        return custom_403(request)

    if request.method != 'GET':
        return custom_405(request, request.method)

    if not hasattr(dash.creator, 'userworkspace'):
        create_workspace(dash.creator)

    name = dash.creator.first_name.encode('utf-8', 'ignore').decode('ascii', 'ignore')
    jwt_key = utils.get_jwt_key(name, [dash.projectrole.backend_role, dash.creator.userworkspace.backend_role])

    url = "{}/app/kibana?jwtToken={}&security_tenant={}#/dashboard/a9513820-41c0-11ea-a32a-715577273fe3".format(
        KIB_OUT_URL,
        jwt_key,
        dash.creator.userworkspace.tenant_name
    )

    return HttpResponseRedirect(url)


def create_workspace(user):
    """
    Create a Tenant for the user and the necessary roles associated
    :param user:
    :return:
    """
    tenant_name = f'tenant_workspace_{user.id}'
    tenant_role = f'role_workspace_{user.id}'
    backend_role = f'br_workspace_{user.id}'
    UserWorkspace.objects.create(user=user,
                                 tenant_name=tenant_name,
                                 tenant_role=tenant_role,
                                 backend_role=backend_role)
    odfe_api = OpendistroApi(ES_IN_URL, ES_ADMIN_PASSWORD)
    odfe_api.create_tenant(tenant_name)
    permissions = {
        "index_permissions": [{
            'index_patterns': [f'?kibana_*_tenantworkspace{user.id}'],
            'allowed_actions': [
                'read', 'delete', 'manage', 'index'
            ]
        }],
        "cluster_permissions": [],
        "tenant_permissions": [{
            "tenant_patterns": [
                tenant_name
            ],
            "allowed_actions": [
                "kibana_all_write"
            ]
        }]
    }
    odfe_api.create_role(tenant_role, permissions=permissions)
    odfe_api.create_mapping(role=tenant_role, backend_roles=[backend_role])

    # Import global objects
    obj = kibana_objects.export_all_objects(KIB_IN_URL, ES_ADMIN_PASSWORD, "global")
    kibana_objects.import_object(KIB_IN_URL, ES_ADMIN_PASSWORD, obj, tenant_name)


def remove_workspace(user):
    """
    Remove the Tenant of a user and all the roles associated
    :param user:
    :return:
    """
    odfe_api = OpendistroApi(ES_IN_URL, ES_ADMIN_PASSWORD)
    odfe_api.delete_mapping(user.userworkspace.tenant_role)
    odfe_api.delete_role(user.userworkspace.tenant_role)
    odfe_api.delete_tenant(user.userworkspace.tenant_name)
    user.userworkspace.delete()


def request_public_kibana(request, dash_id):
    """
    Redirect to Kibana
    :param request:
    :param dash_id:
    :return:
    """
    dash = Dashboard.objects.filter(id=dash_id).first()
    if not dash:
        return custom_404(request, "The project requested was not found in this server")

    if request.method != 'GET':
        return custom_405(request, request.method)

    jwt_key = utils.get_jwt_key(f"Public {dash_id}", dash.projectrole.backend_role)

    url = f"{KIB_OUT_URL}/app/kibana" \
          f"?jwtToken={jwt_key}&security_tenant=global#/dashboard/a834f080-41b1-11ea-a32a-715577273fe3"

    return HttpResponseRedirect(url)


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
    context['gh_uri_identity'] = GitHubOAuth.AUTH_URL
    context['gh_client_id'] = settings.GH_CLIENT_ID
    context['gl_uri_identity'] = GitLabOAuth.AUTH_URL
    context['gl_client_id'] = settings.GL_CLIENT_ID
    context['gl_uri_redirect'] = "https://{}{}".format(request.get_host(), GitLabOAuth.REDIRECT_PATH)
    context['meetup_uri_identity'] = MeetupOAuth.AUTH_URL
    context['meetup_client_id'] = settings.MEETUP_CLIENT_ID
    context['meetup_uri_redirect'] = "https://{}{}".format(request.get_host(), MeetupOAuth.REDIRECT_PATH)

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

    # Message that should be shown to the user
    context['alert_notification'] = request.session.pop('alert_notification', None)

    # Information about the accounts connected
    context['github_enabled'] = hasattr(request.user, 'githubuser')
    context['gitlab_enabled'] = hasattr(request.user, 'gitlabuser')
    context['meetup_enabled'] = hasattr(request.user, 'meetupuser')

    # Matomo link
    context['matomo_enabled'] = settings.MATOMO_ENABLED
    context['matomo_url'] = settings.MATOMO_URL

    # Information about Hatstall
    if HATSTALL_ENABLED:
        context['hatstall_url'] = "/hatstall"

    # Google Analytics
    if GOOGLE_ANALYTICS_ID:
        context['google_analytics_id'] = GOOGLE_ANALYTICS_ID

    return context


def request_dash_summary(request, dash_id):
    summary = get_dashboard_summary(dash_id)
    return JsonResponse(summary)


def request_repos_info(request):
    info = []

    repos_ids = request.GET.getlist('repos_ids')
    try:
        repos = Repository.objects.filter(pk__in=repos_ids)
    except ValueError:
        return JsonResponse(info, safe=False)

    for repo in repos:
        info.append({
            'id': repo.id,
            'status': repo.status,
            'last_refresh': repo.last_refresh,
            'duration': repo.duration,
        })

    return JsonResponse(info, safe=False)


def request_projects_info(request):
    info = []

    projects_ids = request.GET.getlist('projects_ids')
    try:
        projects = Dashboard.objects.filter(pk__in=projects_ids)
    except ValueError:
        return JsonResponse(info, safe=False)

    for project in projects:
        info.append(get_dashboard_summary(project.id))

    return JsonResponse(info, safe=False)


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


def get_gl_repos(owner, token, forks=False):
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


def status_info():
    """
    Retrieve the status info about the server
    :return:
    """
    context = dict()

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

    return context


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
        return render(request, 'cauldronapp/error.html', status=403,
                      context=context)
    if request.method != 'GET':
        context['title'] = "Method Not Allowed"
        context['description'] = "Only GET methods allowed"
        return render(request, 'cauldronapp/error.html', status=405,
                      context=context)

    dashboards = Dashboard.objects.all()
    if dashboards:
        search = request.GET.get('search')
        if search is not None:
            query = Q(creator__first_name__icontains=search) | Q(name__icontains=search)
            dashboards = dashboards.filter(query)

        sort_by = request.GET.get('sort_by')
        if sort_by is not None and sort_by in Dashboard.SORT_CHOICES:
            reverse = False
            if sort_by[0] == '-':
                reverse = True
                sort_by = sort_by[1:]

            if sort_by == 'name':
                dashboards = sorted(dashboards, key=lambda d: d.name, reverse=reverse)
            elif sort_by == 'owner':
                dashboards = sorted(dashboards, key=lambda d: d.creator.first_name, reverse=reverse)
            elif sort_by == 'created':
                dashboards = sorted(dashboards, key=lambda d: d.created, reverse=reverse)
            elif sort_by == 'modified':
                dashboards = sorted(dashboards, key=lambda d: d.modified, reverse=reverse)
            elif sort_by == 'total_tasks':
                dashboards = sorted(dashboards, key=lambda d: d.tasks_count, reverse=reverse)
            elif sort_by == 'completed_tasks':
                dashboards = sorted(dashboards, key=lambda d: d.completed_tasks_count, reverse=reverse)
            elif sort_by == 'running_tasks':
                dashboards = sorted(dashboards, key=lambda d: d.running_tasks_count, reverse=reverse)
            elif sort_by == 'pending_tasks':
                dashboards = sorted(dashboards, key=lambda d: d.pending_tasks_count, reverse=reverse)
            elif sort_by == 'error_tasks':
                dashboards = sorted(dashboards, key=lambda d: d.error_tasks_count, reverse=reverse)
            elif sort_by == 'total_repositories':
                dashboards = sorted(dashboards, key=lambda d: d.repos_count, reverse=reverse)
            elif sort_by == 'git':
                dashboards = sorted(dashboards, key=lambda d: d.repos_git_count, reverse=reverse)
            elif sort_by == 'github':
                dashboards = sorted(dashboards, key=lambda d: d.repos_github_count, reverse=reverse)
            elif sort_by == 'gitlab':
                dashboards = sorted(dashboards, key=lambda d: d.repos_gitlab_count, reverse=reverse)
            elif sort_by == 'meetup':
                dashboards = sorted(dashboards, key=lambda d: d.repos_meetup_count, reverse=reverse)

        p = Pages(dashboards, 10)
        page_number = request.GET.get('page', 1)
        page_obj = p.pages.get_page(page_number)
        context['page_obj'] = page_obj
        context['pages_to_show'] = p.pages_to_show(page_obj.number)
        context['dashboards'] = page_obj.object_list

    context.update(status_info())

    return render(request, 'cauldronapp/admin.html', context=context)


def admin_page_users(request):
    """
    View for the administration page to show an overview of each user
    :param request:
    :return:
    """
    context = create_context(request)

    if not request.user.is_authenticated or not request.user.is_superuser:
        context['title'] = "User Not Allowed"
        context['description'] = "Only Admin users allowed"
        return render(request, 'cauldronapp/error.html', status=403,
                      context=context)
    if request.method != 'GET':
        context['title'] = "Method Not Allowed"
        context['description'] = "Only GET methods allowed"
        return render(request, 'cauldronapp/error.html', status=405,
                      context=context)

    users = User.objects.all()

    search = request.GET.get('search')
    if search is not None:
        users = users.filter(first_name__icontains=search)

    sort_by = request.GET.get('sort_by')
    if sort_by is not None:
        reverse = False
        if sort_by[0] == '-':
            reverse = True
            sort_by = sort_by[1:]

        if sort_by == 'name':
            users = sorted(users, key=lambda u: u.first_name, reverse=reverse)
        elif sort_by == 'joined':
            users = sorted(users, key=lambda u: u.date_joined, reverse=reverse)
        elif sort_by == 'dashboards':
            users = sorted(users, key=lambda u: u.dashboard_set.count(), reverse=reverse)
        elif sort_by == 'admin':
            users = sorted(users, key=lambda u: u.is_superuser, reverse=reverse)

    p = Pages(users, 10)
    page_number = request.GET.get('page', 1)
    page_obj = p.pages.get_page(page_number)
    context['page_obj'] = page_obj
    context['pages_to_show'] = p.pages_to_show(page_obj.number)

    context['users'] = []
    for user in page_obj.object_list:
        user_entry = dict()
        user_entry['user'] = user
        user_entry['tokens'] = {
            'github': Token.objects.filter(backend='github', user=user).first(),
            'gitlab': Token.objects.filter(backend='gitlab', user=user).first(),
            'meetup': Token.objects.filter(backend='meetup', user=user).first(),
        }
        context['users'].append(user_entry)

    context.update(status_info())

    return render(request, 'cauldronapp/admin-users.html', context=context)


def upgrade_user(request):
    """
    Upgrade user to admin
    """
    context = create_context(request)

    if request.method != 'POST':
        context['title'] = "Not allowed"
        context['description'] = "Method not allowed for this path"
        return render(request, 'cauldronapp/error.html', status=405,
                      context=context)

    user_pk = request.POST.get('user_pk', None)
    user = User.objects.filter(pk=user_pk).first()
    if not user:
        context['title'] = "User not found"
        context['description'] = "The user requested was not found in this server"
        return render(request, 'cauldronapp/error.html', status=405,
                      context=context)

    if not request.user.is_superuser:
        context['title'] = "Not allowed"
        context['description'] = "You are not allowed to make this action"
        return render(request, 'cauldronapp/error.html', status=400,
                      context=context)

    # Upgrade user to admin
    upgrade_to_admin(user)

    return HttpResponseRedirect(reverse('admin_page_users'))


def downgrade_user(request):
    """
    Downgrade admin to user
    """
    context = create_context(request)

    if request.method != 'POST':
        context['title'] = "Not allowed"
        context['description'] = "Method not allowed for this path"
        return render(request, 'cauldronapp/error.html', status=405,
                      context=context)

    user_pk = request.POST.get('user_pk', None)
    user = User.objects.filter(pk=user_pk).first()
    if not user:
        context['title'] = "User not found"
        context['description'] = "The user requested was not found in this server"
        return render(request, 'cauldronapp/error.html', status=405,
                      context=context)

    if not request.user.is_superuser:
        context['title'] = "Not allowed"
        context['description'] = "You are not allowed to make this action"
        return render(request, 'cauldronapp/error.html', status=400,
                      context=context)

    # Downgrade admin to user
    user.is_superuser = False
    user.is_staff = False
    user.save()

    return HttpResponseRedirect(reverse('admin_page_users'))


def request_delete_user(request):
    """
    Deletes a user
    """
    context = create_context(request)

    if request.method != 'POST':
        context['title'] = "Not allowed"
        context['description'] = "Method not allowed for this path"
        return render(request, 'error.html', status=405,
                      context=context)

    user_pk = request.POST.get('user_pk', None)
    user = User.objects.filter(pk=user_pk).first()
    if not user:
        context['title'] = "User not found"
        context['description'] = "The user requested was not found in this server"
        return render(request, 'error.html', status=404,
                      context=context)

    if not request.user.is_superuser:
        context['title'] = "Not allowed"
        context['description'] = "You are not allowed to make this action"
        return render(request, 'error.html', status=400,
                      context=context)

    if user == request.user:
        context['title'] = "Not allowed"
        context['description'] = "You are not allowed to delete your own user from the admin page. " \
                                 "Please, go to your settings page to make this action."
        return render(request, 'error.html', status=400,
                      context=context)

    # Delete the user
    delete_user(user)

    return HttpResponseRedirect(reverse('admin_page_users'))


def stats_page(request):
    """
    View for the stats page to show an overview of the server stats
    :param request:
    :return:
    """
    context = create_context(request)

    if request.method != 'GET':
        context['title'] = "Method Not Allowed"
        context['description'] = "Only GET methods allowed"
        return render(request, 'cauldronapp/error.html', status=405,
                      context=context)

    context.update(status_info())

    return render(request, 'cauldronapp/stats.html', context=context)


def terms(request):
    """
    View to show the Terms and Legal Notice about Cauldron
    :param request:
    :return:
    """
    context = create_context(request)
    return render(request, 'cauldronapp/terms.html', context=context)


def privacy(request):
    """
    View to show the Privacy Policy of Cauldron
    :param request:
    :return:
    """
    context = create_context(request)
    return render(request, 'cauldronapp/privacy.html', context=context)


def cookies(request):
    """
    View to show the Cookie Policy of Cauldron
    :param request:
    :return:
    """
    context = create_context(request)
    return render(request, 'cauldronapp/cookies.html', context=context)


def custom_403(request):
    """
    View to show the default 403 template
    :param request:
    :return:
    """
    context = create_context(request)
    context['title'] = "403 Forbidden"
    context['description'] = "You do not have the necessary permissions to perform this action"
    return render(request, 'cauldronapp/error.html', status=403, context=context)


def custom_404(request, message):
    """
    View to show the default 404 template
    :param request:
    :param message:
    :return:
    """
    context = create_context(request)
    context['title'] = "404 Not Found"
    context['description'] = message
    return render(request, 'cauldronapp/error.html', status=404, context=context)


def custom_405(request, method):
    """
    View to show the default 405 template
    :param request:
    :param method:
    :return:
    """
    context = create_context(request)
    context['title'] = "405 Method not allowed"
    context['description'] = f"Method {method} is not allowed in this resource"
    return render(request, 'cauldronapp/error.html', status=405, context=context)


def custom_500(request, message):
    """
    View to show the default 500 template
    :param request:
    :param message:
    :return:
    """
    context = create_context(request)
    context['title'] = "500 Internal server error"
    context['description'] = message
    return render(request, 'cauldronapp/error.html', status=500, context=context)
