from django.shortcuts import render
from django.http import HttpResponseRedirect, JsonResponse
from django.contrib.auth import login, logout, get_user_model
from django.urls import reverse
from django.db import transaction
from django.views.decorators.http import require_http_methods

from CauldronApp.pages import Pages
from CauldronApp import kibana_objects, utils
from CauldronApp.project_metrics import metrics
from CauldronApp import datasources

from cauldron_apps.poolsched_github.models import GHToken, IGHRaw
from cauldron_apps.poolsched_gitlab.models import GLToken, GLInstance, IGLRaw
from cauldron_apps.poolsched_meetup.models import MeetupToken, IMeetupRaw
from cauldron_apps.cauldron.models import IAddGHOwner, IAddGLOwner
from cauldron_apps.poolsched_export.models.iexportgit import IExportGitCSV
from poolsched.models import Intention, ArchivedIntention
from poolsched.models.jobs import Log

import logging
import datetime
from random import choice
from string import ascii_lowercase, digits
from urllib.parse import urlencode
from dateutil.relativedelta import relativedelta

from Cauldron2.settings import ES_IN_HOST, ES_IN_PORT, ES_IN_PROTO, ES_ADMIN_PASSWORD, \
                               KIB_IN_HOST, KIB_IN_PORT, KIB_IN_PROTO, KIB_OUT_URL, \
                               KIB_PATH
from Cauldron2 import settings

from CauldronApp.models import Project, GithubUser, GitlabUser, MeetupUser, GnomeUser, \
    AnonymousUser, UserWorkspace, ProjectRole
from CauldronApp.models import Repository, GitLabRepository, GitRepository, GitHubRepository, MeetupRepository

from cauldron_apps.cauldron.opendistro import OpendistroApi
from CauldronApp.oauth.github import GitHubOAuth
from CauldronApp.oauth.gitlab import GitLabOAuth
from CauldronApp.oauth.meetup import MeetupOAuth

from .project_metrics.metrics import get_compare_metrics, get_compare_charts

import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

User = get_user_model()

JOB_LOGS = '/job_logs'

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
        projects = Project.objects.filter(creator=request.user)

        search = request.GET.get('search')
        if search is not None:
            projects = projects.filter(name__icontains=search)

        p = Pages(projects, 9)
        page_number = request.GET.get('page', 1)
        page_obj = p.pages.get_page(page_number)
        context['page_obj'] = page_obj
        context['pages_to_show'] = p.pages_to_show(page_obj.number)

        projects_info = list()
        for project in page_obj.object_list:
            summary = project.summary()
            summary['project'] = project
            projects_info.append(summary)
        context['projects_info'] = projects_info
    return render(request, 'cauldronapp/projects/projects.html', context=context)


# TODO: Add state
def request_github_oauth(request):
    """Callback for GitHub authentication"""
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
    if merged:
        request.session['alert_notification'] = {'title': 'Account merged',
                                                 'message': f"You already had a Cauldron user with this GitHub account."
                                                            f" We have proceeded to merge all the projects and "
                                                            f"visualization in you current account so that you do not "
                                                            f"loose anything"}
    GHToken.objects.update_or_create(user=request.user, defaults={'token': oauth_user.token})

    if data_add and data_add['backend'] == 'github':
        project = Project.objects.filter(id=data_add['proj_id']).first()
        datasources.github.analyze_data(project,
                                        data_add['data'], data_add['commits'],
                                        data_add['issues'], data_add['forks'])

    if last_page:
        return HttpResponseRedirect(last_page)

    return HttpResponseRedirect(reverse('homepage'))


def merge_accounts(user_origin, user_dest):
    """Change the references of that user to another one"""
    GithubUser.objects.filter(user=user_origin).update(user=user_dest)
    GitlabUser.objects.filter(user=user_origin).update(user=user_dest)
    MeetupUser.objects.filter(user=user_origin).update(user=user_dest)
    GnomeUser.objects.filter(user=user_origin).update(user=user_dest)
    Project.objects.filter(creator=user_origin).update(creator=user_dest)
    GHToken.objects.filter(user=user_origin).update(user=user_dest)
    GLToken.objects.filter(user=user_origin).update(user=user_dest)
    MeetupToken.objects.filter(user=user_origin).update(user=user_dest)
    merge_workspaces(user_origin, user_dest)
    merge_admins(user_origin, user_dest)


def merge_admins(old_user, new_user):
    """Convert the new user to admin if the old one was an admin"""
    new_user.is_staff = new_user.is_staff or old_user.is_staff
    new_user.is_superuser = new_user.is_superuser or old_user.is_superuser
    new_user.save()


def merge_workspaces(old_user, new_user):
    """Rewrite all the visualizations from one tenant to the other one"""
    if not hasattr(old_user, 'userworkspace'):
        return
    if not hasattr(new_user, 'userworkspace'):
        create_workspace(new_user)
    obj = kibana_objects.export_all_objects(KIB_IN_URL, ES_ADMIN_PASSWORD, old_user.userworkspace.tenant_name)
    kibana_objects.import_object(KIB_IN_URL, ES_ADMIN_PASSWORD, obj, new_user.userworkspace.tenant_name)


# TODO: Add state
def request_gitlab_oauth(request):
    redirect_uri = request.build_absolute_uri(reverse('gitlab_callback')).replace('http', 'https')
    code = request.GET.get('code', None)
    if not code:
        return custom_404(request, "Code not found in the GitLab callback")
    gitlab = GitLabOAuth(settings.GL_CLIENT_ID, settings.GL_CLIENT_SECRET, redirect_uri, instance=GitLabOAuth.GITLAB)
    error = gitlab.authenticate(code)
    if error:
        return custom_500(request, error)
    oauth_user = gitlab.user_data()

    is_admin = oauth_user.username in settings.CAULDRON_ADMINS['GITLAB']

    # Save the state of the session
    data_add = request.session.pop('add_repo', None)
    last_page = request.session.pop('last_page', None)

    merged = authenticate_user(request, GitlabUser, oauth_user, is_admin)
    if merged:
        request.session['alert_notification'] = {'title': 'Account merged',
                                                 'message': f"You already had a Cauldron user with this GitLab account."
                                                            f" We have proceeded to merge all the projects and "
                                                            f"visualization in you current account so that you do not "
                                                            f"loose anything"}

    instance = GLInstance.objects.get(name='GitLab')
    GLToken.objects.update_or_create(user=request.user, instance=instance, defaults={'token': oauth_user.token})

    if data_add and data_add['backend'] == 'gitlab':
        project = Project.objects.get(id=data_add['proj_id'])
        datasources.gitlab.analyze_data(project,
                                        data_add['data'], data_add['commits'],
                                        data_add['issues'], data_add['forks'],
                                        instance='GitLab')
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
    redirect_uri = request.build_absolute_uri(reverse('meetup_callback')).replace('http', 'https')
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
    if merged:
        request.session['alert_notification'] = {'title': 'Account merged',
                                                 'message': f"You already had a Cauldron user with this Meetup account."
                                                            f" We have proceeded to merge all the projects and "
                                                            f"visualization in you current account so that you do not "
                                                            f"loose anything"}

    MeetupToken.objects.update_or_create(user=request.user, defaults={'token': oauth_user.token,
                                                                      'refresh_token': oauth_user.refresh_token})

    if data_add and data_add['backend'] == 'meetup':
        project = Project.objects.get(id=data_add['proj_id'])
        datasources.meetup.analyze_data(project, data_add['data'])

    if last_page:
        return HttpResponseRedirect(last_page)

    return HttpResponseRedirect(reverse('homepage'))


def request_gnome_callback(request):
    redirect_uri = request.build_absolute_uri(reverse('gnome_callback')).replace('http', 'https')
    code = request.GET.get('code', None)
    gitlab = GitLabOAuth(settings.GNOME_CLIENT_ID, settings.GNOME_CLIENT_SECRET, redirect_uri, GitLabOAuth.GNOME)
    error = gitlab.authenticate(code)
    if error:
        return custom_404(request, error)
    oauth_user = gitlab.user_data()

    is_admin = oauth_user.username in settings.CAULDRON_ADMINS['GNOME']

    # Take the state of the session before authentication
    data_add = request.session.pop('add_repo', None)
    last_page = request.session.pop('last_page', None)

    merged = authenticate_user(request, GnomeUser, oauth_user, is_admin)
    if merged:
        request.session['alert_notification'] = {'title': 'Account merged',
                                                 'message': f"You already had a Cauldron user with this GitLab account."
                                                            f" We have proceeded to merge all the projects and "
                                                            f"visualization in you current account so that you do not "
                                                            f"loose anything"}
    instance = GLInstance.objects.get(name='Gnome')
    GLToken.objects.update_or_create(user=request.user, instance=instance, defaults={'token': oauth_user.token})

    if data_add and data_add['backend'] == 'gnome':
        project = Project.objects.get(id=data_add['proj_id'])
        datasources.gitlab.analyze_data(project,
                                        data_add['data'], data_add['commits'],
                                        data_add['issues'], data_add['forks'],
                                        instance='Gnome')
        project.update_elastic_role()
    if last_page:
        return HttpResponseRedirect(last_page)

    return HttpResponseRedirect(reverse('homepage'))


def authenticate_user(request, backend_model, oauth_user, is_admin=False):
    """
    Authenticate an oauth request and merge with existent accounts if needed
    :param request: request from login callback
    :param backend_model: GitlabUser, GithubUser, MeetupUser, GnomeUser ...
    :param oauth_user: user information obtained from the backend
    :param is_admin: flag to indicate that the user to authenticate is an admin
    :return: boolean. The user has been merged
    """
    merged = False
    backend_entity = backend_model.objects.filter(username=oauth_user.username).first()
    backend_user = backend_entity.user if backend_entity else None

    if backend_user:
        if request.user.is_authenticated and backend_user != request.user:
            # Someone is authenticated, backend user exists and aren't the same account
            merge_accounts(user_origin=request.user, user_dest=backend_user)
            request.user.delete()
            login(request, backend_user)
            merged = True
        else:
            # No one is authenticated and backend user exists
            login(request, backend_user)
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

        # Create the backend entity and associate with the account
        backend_model.objects.create(user=request.user, username=oauth_user.username, photo=oauth_user.photo)

    return merged


def create_django_user(name):
    """Create a django user with a random username and unusable password"""
    dj_name = generate_random_uuid(length=96)
    dj_user = User.objects.create_user(username=dj_name, first_name=name)
    dj_user.set_unusable_password()
    dj_user.save()
    return dj_user


def upgrade_to_admin(user):
    """Upgrades a user to Cauldron Admin"""
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


def project_common(request, project_id):
    """Create common items for the project. Return project object and context.
    If project does not exist, raise exception"""
    project = Project.objects.get(pk=project_id)
    context = create_context(request)
    context['project'] = project
    context['repositories_count'] = project.repository_set.count()
    context['has_git'] = GitRepository.objects.filter(projects=project).exists()
    context['editable'] = ((request.user.is_authenticated and request.user == project.creator) or
                           request.user.is_superuser)
    if request.user.is_authenticated:
        context['projects_compare'] = request.user.project_set.exclude(pk=project.pk)

    return project, context


def request_show_project(request, project_id):
    """ View for a project and metrics"""
    if request.method != 'GET':
        return custom_405(request, request.method)

    try:
        project, context = project_common(request, project_id)
    except Project.DoesNotExist:
        return custom_404(request, "The project requested was not found in this server")

    context['render_table'] = False
    context['has_git'] = GitRepository.objects.filter(projects=project).exists()
    context['has_github'] = GitHubRepository.objects.filter(projects=project).exists()
    context['has_gitlab'] = GitLabRepository.objects.filter(projects=project).exists()
    context['has_meetup'] = MeetupRepository.objects.filter(projects=project).exists()
    context['repos'] = project.repository_set.all().select_subclasses()

    return render(request, 'cauldronapp/project/project.html', context=context)


def request_project_repositories(request, project_id):
    """ View for the repositories of a project"""
    if request.method != 'GET':
        return custom_405(request, request.method)

    try:
        project, context = project_common(request, project_id)
    except Project.DoesNotExist:
        return custom_404(request, "The project requested was not found in this server")

    context['render_table'] = True
    repositories = project.repository_set.all()
    p = Pages(repositories.select_subclasses(), 10)
    page_number = request.GET.get('page', 1)
    page_obj = p.pages.get_page(page_number)
    context['page_obj'] = page_obj
    context['pages_to_show'] = p.pages_to_show(page_obj.number)

    return render(request, 'cauldronapp/project/project.html', context=context)


def request_repo_actions(request, repo_id):
    """View for a repository. It shows all the intentions related"""
    context = create_context(request)
    try:
        repo = Repository.objects.get_subclass(id=repo_id)
    except Repository.DoesNotExist:
        return custom_404(request, 'Repository not found in this server')

    context['repo'] = repo
    context['intentions'] = repo.get_intentions()

    return render(request, 'cauldronapp/project/repo_actions.html', context=context)


def request_logs(request, logs_id):
    """View logs"""
    try:
        logs_obj = Log.objects.get(id=logs_id)
    except Intention.DoesNotExist:
        return JsonResponse({'logs': "Logs not found for this action. Could not have started yet."})

    try:
        with open(f"{JOB_LOGS}/{logs_obj.location}", 'r') as f:
            logs = f.read()
    except FileNotFoundError:
        logs = "Logs not found for this action. Could not have started yet."

    return JsonResponse({'content': logs, 'more': logs_obj.job_set.exists()})


@require_http_methods(['POST'])
def request_add_to_project(request, project_id):
    """ Add new repositories to a project"""
    project = Project.objects.filter(id=project_id).first()
    if not project:
        return JsonResponse({'status': 'error', 'message': 'Project not found'}, status=404)
    if not request.user.is_authenticated or (request.user != project.creator and not request.user.is_superuser):
        return JsonResponse({'status': 'error', 'message': 'You cannot edit this project'}, status=403)

    backend = request.POST.get('backend', None)
    data = request.POST.get('data', None)  # Could be url or user

    if not backend or not data:
        return JsonResponse({'status': 'error', 'message': 'Backend or data missing'},
                            status=400)

    if backend == 'git':
        data = data.strip()
        datasources.git.analyze_git(project, data)
        project.update_elastic_role()
        return JsonResponse({'status': 'ok'})

    if backend == 'github':
        analyze_commits = 'commits' in request.POST
        analyze_issues = 'issues' in request.POST
        forks = 'forks' in request.POST
        if not project.creator.ghtokens.filter(instance='GitHub').exists():
            if request.user != project.creator:
                return JsonResponse({'status': 'error',
                                     'message': 'Project owner needs a GitHub token '
                                                'to analyze this kind of repositories'},
                                    status=401)
            request.session['add_repo'] = {'data': data,
                                           'backend': backend,
                                           'proj_id': project.id,
                                           'commits': analyze_commits,
                                           'forks': forks,
                                           'issues': analyze_issues}
            request.session['last_page'] = reverse('show_project', kwargs={'project_id': project.id})
            params = urlencode({'client_id': settings.GH_CLIENT_ID})
            gh_url_oauth = f"{GitHubOAuth.AUTH_URL}?{params}"
            return JsonResponse({'status': 'error',
                                 'message': generate_request_token_message("GitHub"),
                                 'redirect': gh_url_oauth},
                                status=401)
        output = datasources.github.analyze_data(project=project, data=data, commits=analyze_commits,
                                                 issues=analyze_issues, forks=forks)

        return JsonResponse(output, status=output['code'])

    elif backend == 'gitlab':
        analyze_commits = 'commits' in request.POST
        analyze_issues = 'issues' in request.POST
        forks = 'forks' in request.POST
        if not project.creator.gltokens.filter(instance='GitLab').exists():
            if request.user != project.creator:
                return JsonResponse({'status': 'error',
                                     'message': 'Project owner needs a GitLab token to '
                                                'analyze this kind of repositories'},
                                    status=401)
            request.session['add_repo'] = {'data': data,
                                           'backend': backend,
                                           'proj_id': project.id,
                                           'commits': analyze_commits,
                                           'forks': forks,
                                           'issues': analyze_issues}
            request.session['last_page'] = reverse('show_project', kwargs={'project_id': project.id})
            redirect_uri = request.build_absolute_uri(reverse('gitlab_callback')).replace('http', 'https')
            params = urlencode({'client_id': settings.GL_CLIENT_ID,
                                'response_type': 'code',
                                'redirect_uri': redirect_uri})
            gl_url_oauth = f"{GitLabOAuth.INSTANCES['GitLab']['auth_url']}?{params}"
            return JsonResponse({'status': 'error',
                                 'message': generate_request_token_message("GitLab"),
                                 'redirect': gl_url_oauth},
                                status=401)
        output = datasources.gitlab.analyze_data(project=project, data=data, commits=analyze_commits,
                                                 issues=analyze_issues, forks=forks)
        return JsonResponse(output, status=output['code'])

    elif backend == 'gnome':
        analyze_commits = 'commits' in request.POST
        analyze_issues = 'issues' in request.POST
        forks = 'forks' in request.POST
        if not project.creator.gltokens.filter(instance='Gnome').exists():
            if request.user != project.creator:
                return JsonResponse({'status': 'error',
                                     'message': 'Project owner needs a GitLab(GNOME) token to '
                                                'analyze this kind of repositories'},
                                    status=401)
            request.session['add_repo'] = {'data': data,
                                           'backend': backend,
                                           'proj_id': project.id,
                                           'commits': analyze_commits,
                                           'forks': forks,
                                           'issues': analyze_issues}
            request.session['last_page'] = reverse('show_project', kwargs={'project_id': project.id})
            redirect_uri = request.build_absolute_uri(reverse('gnome_callback')).replace('http', 'https')
            params = urlencode({'client_id': settings.GNOME_CLIENT_ID,
                                'response_type': 'code',
                                'redirect_uri': redirect_uri})
            gl_url_oauth = f"{GitLabOAuth.INSTANCES['Gnome']['auth_url']}?{params}"
            return JsonResponse({'status': 'error',
                                 'message': generate_request_token_message("GitLab for Gnome"),
                                 'redirect': gl_url_oauth},
                                status=401)
        output = datasources.gitlab.analyze_data(project=project, data=data, commits=analyze_commits,
                                                 issues=analyze_issues, forks=forks, instance='Gnome')
        project.update_elastic_role()
        return JsonResponse(output, status=output['code'])

    elif backend == 'meetup':
        if not project.creator.meetuptokens.exists():
            if request.user != project.creator:
                return JsonResponse({'status': 'error',
                                     'message': 'Project owner needs a Meetup token to'
                                                ' analyze this kind of repositories'},
                                    status=401)
            request.session['add_repo'] = {'data': data, 'backend': backend, 'proj_id': project.id}
            request.session['last_page'] = reverse('show_project', kwargs={'project_id': project.id})
            params = urlencode({'client_id': settings.MEETUP_CLIENT_ID,
                                'response_type': 'code',
                                'redirect_uri': "https://{}{}".format(request.get_host(),
                                                                      MeetupOAuth.REDIRECT_PATH)})
            meetup_url_oauth = "{}?{}".format(MeetupOAuth.AUTH_URL, params)
            return JsonResponse({'status': 'error',
                                 'message': generate_request_token_message("Meetup"),
                                 'redirect': meetup_url_oauth},
                                status=401)

        output = datasources.meetup.analyze_data(project=project, data=data)
        return JsonResponse(output, status=output['code'])

    else:
        return JsonResponse({'status': 'error', 'message': 'Backend not found'},
                            status=400)


@require_http_methods(["POST"])
def request_remove_from_project(request, project_id):
    project = Project.objects.filter(id=project_id).first()
    if not project:
        return JsonResponse({'status': 'error', 'message': 'Project not found'}, status=404)
    if not request.user.is_authenticated or (request.user != project.creator and not request.user.is_superuser):
        return JsonResponse({'status': 'error', 'message': 'You cannot edit this project'}, status=403)

    repo_id = request.POST.get('repository', None)

    if not repo_id:
        return JsonResponse({'status': 'error', 'message': 'We need a url to delete'},
                            status=400)

    try:
        repo = Repository.objects.get_subclass(id=repo_id)
    except Repository.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Repository not found'},
                            status=404)
    repo.projects.remove(project)
    project.update_elastic_role()
    repo.remove_intentions(request.user)
    repo.create_remove_action(project)
    return JsonResponse({'status': 'deleted'})


@require_http_methods(["POST"])
def request_rename_project(request, project_id):
    """Update the name for a project"""
    try:
        project = Project.objects.get(id=project_id)
    except Project.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': f"Project {project_id} does not exist"},
                            status=404)
    if not request.user.is_authenticated and request.user != project.creator and not request.user.is_superuser:
        return JsonResponse({'status': 'error', 'message': f'You cannot edit project {project_id}, '
                                                           f'you are not the owner'},
                            status=400)

    name = request.POST.get('name', '').strip()

    if len(name) < 1 or len(name) > 32:
        return JsonResponse({'status': 'error', 'message': "The name doesn't fit the allowed length "},
                            status=400)

    if Project.objects.filter(creator=project.creator, name=name).exists():
        return JsonResponse({'status': 'Duplicated name', 'message': 'You have the same name in another Project'},
                            status=400)
    project.name = name
    project.save()
    return JsonResponse({'status': 'Ok', 'message': 'Name updated successfully'})


def request_new_project(request):
    """Create a new project and redirect to project"""
    if request.method != 'POST':
        return custom_405(request, request.method)

    if not request.user.is_authenticated:
        user = User.objects.create_user(username=generate_random_uuid(length=96),
                                        first_name="Anonymous")
        user.set_unusable_password()
        user.save()
        anonym_user = AnonymousUser(user=user)
        anonym_user.save()
        login(request, user)

    project = Project.objects.create(name='My project', creator=request.user)
    project.name = f"Project {project.id}"
    project.save()
    create_es_role(project)

    # TODO: If something is wrong delete the project
    return HttpResponseRedirect(reverse('show_project', kwargs={'project_id': project.id}))


def create_es_role(project):
    if hasattr(project, 'projectrole'):
        return
    role = f"role_project_{project.id}"
    backend_role = f"br_project_{project.id}"

    od_api = OpendistroApi(ES_IN_URL, settings.ES_ADMIN_PASSWORD)
    od_api.create_role(role)
    od_api.create_mapping(role, backend_roles=[backend_role])

    ProjectRole.objects.create(role=role, backend_role=backend_role, project=project)


def request_refresh_project(request, project_id):
    """Refresh all the project"""
    try:
        project = Project.objects.get(id=project_id)
    except Project.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': f"Project {project_id} does not exist"},
                            status=404)

    if not request.user.is_authenticated and request.user != project.creator and not request.user.is_superuser:
        return JsonResponse({'status': 'error', 'message': f'You cannot edit project {project_id}, '
                                                           f'you are not the owner'},
                            status=400)

    refresh_count = 0
    for repo in project.repository_set.select_subclasses():
        if repo.refresh(project.creator):
            refresh_count += 1

    return JsonResponse({'status': 'reanalyze',
                         'message': f"Refreshing {refresh_count} repositories"})


def request_refresh_repository(request, repo_id):
    """Refresh the selected repository"""
    try:
        repo = Repository.objects.get_subclass(id=repo_id)
    except Repository.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': f"Repository {repo_id} does not exist"},
                            status=404)
    refresh = repo.refresh(request.user)
    if refresh:
        return JsonResponse({'status': 'reanalyze'})
    else:
        return JsonResponse({'status': 'Unable to refresh the selected repository. A token is needed'})


def request_compare_projects(request):
    """View for the project comparison."""
    context = create_context(request)

    if request.method != 'GET':
        return custom_405(request, request.method)

    try:
        projects_id = list(map(int, request.GET.getlist('projects')))
    except ValueError:
        projects_id = []

    if projects_id:
        projects = Project.objects.filter(id__in=projects_id)
    else:
        projects = Project.objects.none()

    if projects.count() > 5:
        return custom_403(request)

    context['projects'] = projects

    if request.user.is_authenticated:
        context['user_projects'] = request.user.project_set.all()

    if projects.filter(repository=None).count() > 0:
        context['message_error'] = "Some of the selected projects do not have repositories..."
        context['projects'] = Project.objects.none()
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

        urls = []
        for project in projects:
            urls.extend(project.url_list())

        if projects.count() > 0:
            context['metrics'] = get_compare_metrics(projects, urls, from_date, to_date)
            context['charts'] = get_compare_charts(projects, urls, from_date, to_date)

    return render(request, 'cauldronapp/compare/projects_compare.html', context=context)


def request_project_metrics(request, project_id):
    """Obtain the metrics related to a project for a category. By default overview"""
    if request.method != 'GET':
        return custom_405(request, request.method)

    category = request.GET.get('tab', 'overview')

    try:
        project = Project.objects.get(pk=project_id)
    except Project.DoesNotExist:
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

    urls = request.GET.getlist('repo_url[]')
    if not urls:
        urls = project.url_list()

    return JsonResponse(metrics.get_category_metrics(project, category, urls, from_date, to_date))


def request_delete_project(request, project_id):
    if request.method != 'POST':
        return custom_405(request, request.method)

    try:
        project = Project.objects.get(id=project_id)
    except Project.DoesNotExist:
        return custom_404(request, "The project requested was not found in this server")

    owner = request.user.is_authenticated and request.user == project.creator
    if not owner and not request.user.is_superuser:
        return custom_403(request)

    delete_project(project)

    return JsonResponse({'status': 'Ok', 'id': project_id, 'message': 'Project deleted successfully'})


def delete_project(project):
    # Remove tasks in a transaction atomic
    with transaction.atomic():
        for repo in project.repository_set.select_subclasses():
            repo.remove_intentions(project.creator)
    odfe_api = OpendistroApi(ES_IN_URL, ES_ADMIN_PASSWORD)
    odfe_api.delete_mapping(project.projectrole.role)
    odfe_api.delete_role(project.projectrole.role)
    project.delete()


def delete_user(user):
    for project in user.project_set.all():
        delete_project(project)
    if hasattr(user, 'userworkspace'):
        remove_workspace(user)

    user.delete()


def request_workspace(request, project_id):
    """Redirect to My workspace of the requested project or create it"""
    project = Project.objects.filter(id=project_id).first()
    if not project:
        return custom_404(request, "The project requested was not found in this server")

    is_owner = request.user.is_authenticated and request.user == project.creator
    if not is_owner and not request.user.is_superuser:
        return custom_403(request)

    if request.method != 'GET':
        return custom_405(request, request.method)

    if not hasattr(project.creator, 'userworkspace'):
        create_workspace(project.creator)

    name = project.creator.first_name.encode('utf-8', 'ignore').decode('ascii', 'ignore')
    jwt_key = utils.get_jwt_key(name, [project.projectrole.backend_role, project.creator.userworkspace.backend_role])

    url = "{}/app/kibana?jwtToken={}&security_tenant={}#/dashboard/a9513820-41c0-11ea-a32a-715577273fe3".format(
        KIB_OUT_URL,
        jwt_key,
        project.creator.userworkspace.tenant_name
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


def request_public_kibana(request, project_id):
    """Redirect to public Kibana"""
    project = Project.objects.filter(id=project_id).first()
    if not project:
        return custom_404(request, "The project requested was not found in this server")

    if request.method != 'GET':
        return custom_405(request, request.method)

    jwt_key = utils.get_jwt_key(f"Public {project_id}", project.projectrole.backend_role)

    url = f"{KIB_OUT_URL}/app/kibana" \
          f"?jwtToken={jwt_key}&security_tenant=global#/dashboard/a834f080-41b1-11ea-a32a-715577273fe3"

    return HttpResponseRedirect(url)


def request_kibana_admin(request):
    if not request.user.is_authenticated or not request.user.is_superuser:
        return custom_403(request)

    jwt_key = utils.get_jwt_key('admin', 'admin')

    url = "{}/app/discover?jwtToken={}".format(
        KIB_OUT_URL,
        jwt_key
    )
    return HttpResponseRedirect(url)


def request_delete_token(request):
    """Function for deleting a token from a user. It deletes the tasks associate with that token"""
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Only POST methods allowed'}, status=405)

    if not request.user.is_authenticated:
        return JsonResponse({'status': 'error', 'message': 'You are not logged in'}, status=401)

    identity = request.POST.get('identity', None)
    if identity == 'github':
        tokens = request.user.ghtokens.filter(instance='GitHub')
        for token in tokens:
            IGHRaw.objects.filter(user=request.user, job__isnull=True, repo__instance='GitHub').delete()
            IAddGHOwner.objects.filter(user=request.user, job__isnull=True, instance='GitHub').delete()
            token.delete()
        return JsonResponse({'status': 'ok'})
    elif identity == 'gitlab':
        tokens = request.user.gltokens.filter(instance='GitLab')
        for token in tokens:
            IGLRaw.objects.filter(user=request.user, job__isnull=True, repo__instance='GitLab').delete()
            IAddGLOwner.objects.filter(user=request.user, job__isnull=True, instance='GitLab').delete()
            token.delete()
        return JsonResponse({'status': 'ok'})
    elif identity == 'meetup':
        tokens = request.user.meetuptokens.all()
        for token in tokens:
            IMeetupRaw.objects.filter(user=request.user, job__isnull=True).delete()
            token.delete()
        return JsonResponse({'status': 'ok'})
    elif identity == 'gnome':
        tokens = request.user.gltokens.filter(instance='Gnome')
        for token in tokens:
            IGLRaw.objects.filter(user=request.user, job__isnull=True, repo__instance='Gnome').delete()
            IAddGLOwner.objects.filter(user=request.user, job__isnull=True, instance='Gnome').delete()
            token.delete()
        return JsonResponse({'status': 'ok'})
    else:
        return JsonResponse({'status': 'error', 'message': 'Unknown identity: {}'.format(identity)})


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
    context['gl_uri_identity'] = GitLabOAuth.INSTANCES['GitLab']['auth_url']
    context['gl_client_id'] = settings.GL_CLIENT_ID
    context['gl_uri_redirect'] = request.build_absolute_uri(reverse('gitlab_callback')).replace('http', 'https')
    context['gnome_uri_identity'] = GitLabOAuth.INSTANCES['Gnome']['auth_url']
    context['gnome_client_id'] = settings.GNOME_CLIENT_ID
    context['gnome_uri_redirect'] = request.build_absolute_uri(reverse('gnome_callback')).replace('http', 'https')
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
        elif hasattr(request.user, 'gnomeuser'):
            context['photo_user'] = request.user.gnomeuser.photo
        else:
            context['photo_user'] = '/static/img/profile-default.png'

    # Message that should be shown to the user
    context['alert_notification'] = request.session.pop('alert_notification', None)

    # Information about the accounts connected
    context['github_enabled'] = hasattr(request.user, 'githubuser')
    context['gitlab_enabled'] = hasattr(request.user, 'gitlabuser')
    context['meetup_enabled'] = hasattr(request.user, 'meetupuser')
    context['gnome_enabled'] = hasattr(request.user, 'gnomeuser')

    # Matomo link
    context['matomo_enabled'] = settings.MATOMO_ENABLED
    context['matomo_url'] = settings.MATOMO_URL

    # Information about Hatstall
    if settings.HATSTALL_ENABLED:
        context['hatstall_url'] = "/hatstall"

    # Plausible Analytics
    context['plausible_analytics_enabled'] = settings.PLAUSIBLE_ANALYTICS_ENABLED
    context['plausible_analytics_url'] = settings.PLAUSIBLE_ANALYTICS_URL

    # Google Analytics
    if settings.GOOGLE_ANALYTICS_ID:
        context['google_analytics_id'] = settings.GOOGLE_ANALYTICS_ID

    return context


def request_project_summary(request, project_id):
    """Return a JSON with the summary of the project"""
    try:
        project = Project.objects.get(pk=project_id)
    except Project.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'project not found'})
    summary = project.summary()
    return JsonResponse(summary)


def request_ongoing_owners(request, project_id):
    """Return a JSON with the ongoing owners requested"""
    response = {'owners': []}
    gh_owners = IAddGHOwner.objects.filter(project_id=project_id)
    gl_owners = IAddGLOwner.objects.filter(project_id=project_id, instance='GitLab')
    gnome_owners = IAddGLOwner.objects.filter(project_id=project_id, instance='Gnome')
    for gh_owner in gh_owners:
        response['owners'].append({'backend': 'github', 'owner': gh_owner.owner})
    for gl_owner in gl_owners:
        response['owners'].append({'backend': 'gitlab', 'owner': gl_owner.owner})
    for gnome_owner in gnome_owners:
        response['owners'].append({'backend': 'gnome', 'owner': gnome_owner.owner})
    return JsonResponse(response)


def request_create_git_csv(request, project_id):
    try:
        project = Project.objects.get(id=project_id)
    except Project.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'project not found'})
    IExportGitCSV.objects.get_or_create(defaults={'user': request.user}, project=project)
    return JsonResponse({'status': 'ok'})


def request_repos_info(request):
    info = []

    repos_ids = request.GET.getlist('repos_ids')
    try:
        repos = Repository.objects.filter(pk__in=repos_ids)
    except ValueError:
        return JsonResponse(info, safe=False)

    for repo in repos.select_subclasses():
        info.append({
            'id': repo.id,
            'status': repo.status,
            'last_refresh': repo.last_refresh,
        })

    return JsonResponse(info, safe=False)


def request_projects_info(request):
    """Return a summary of each project requested"""
    info = []
    projects_ids = request.GET.getlist('projects_ids')
    try:
        projects = Project.objects.filter(pk__in=projects_ids)
    except ValueError:
        return JsonResponse(info, safe=False)
    for project in projects:
        info.append(project.summary())
    return JsonResponse(info, safe=False)


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

    # Total Projects
    context['total_projects'] = Project.objects.count()
    context['total_projects_with_repos'] = Project.objects.exclude(repository=None).count()
    # Total Users
    context['total_users'] = User.objects.count()
    context['total_users_authenticated'] = User.objects.filter(anonymoususer__isnull=True).count()
    # Total Intentions
    intentions_count = Intention.objects.count()
    context['total_intentions'] = intentions_count + ArchivedIntention.objects.count()
    context['running_intentions'] = intentions_count
    context['success_intentions'] = ArchivedIntention.objects.filter(status=ArchivedIntention.OK).count()
    context['error_intentions'] = ArchivedIntention.objects.filter(status=ArchivedIntention.ERROR).count()
    # Total Repositories
    context['repos_count'] = Repository.objects.exclude(projects=None).count()
    context['repos_git_count'] = GitRepository.objects.exclude(projects=None).count()
    context['repos_github_count'] = GitHubRepository.objects.exclude(projects=None).count()
    context['repos_gitlab_count'] = GitLabRepository.objects.exclude(projects=None, instance='GitLab').count()
    context['repos_gnome_count'] = GitLabRepository.objects.exclude(projects=None, instance='Gnome').count()
    context['repos_meetup_count'] = MeetupRepository.objects.exclude(projects=None).count()
    return context


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
