import logging
import datetime
import os.path

import requests
import random
from random import choice
from string import ascii_lowercase, digits
from dateutil.relativedelta import relativedelta
from django.db.models import Min, Count

from django.shortcuts import render
from django.http import HttpResponseRedirect, JsonResponse
from django.contrib.auth import login, logout, get_user_model
from django.urls import reverse
from django.db import transaction
from django.views.decorators.http import require_http_methods, last_modified
from django.conf import settings

from CauldronApp import kibana_objects, utils, datasources
from CauldronApp.pages import Pages
from CauldronApp.oauth import GitHubOAuth, GitLabOAuth, MeetupOAuth, TwitterOAuth, StackExchangeOAuth
from CauldronApp.project_metrics import metrics

from poolsched.models import Intention, ArchivedIntention, ScheduledIntention
from poolsched.models.jobs import Log
from cauldron_apps.cauldron.models.backends import Backends
from cauldron_apps.poolsched_github.models import GHToken, IGHRaw
from cauldron_apps.poolsched_gitlab.models import GLToken, GLInstance, IGLRaw
from cauldron_apps.poolsched_meetup.models import MeetupToken, IMeetupRaw
from cauldron_apps.poolsched_stackexchange.models import StackExchangeToken, IStackExchangeRaw
from cauldron_apps.poolsched_twitter.models import ITwitterNotify
from cauldron_apps.poolsched_export.models import IExportCSV, IReportKbn, ProjectKibanaReport, \
    ICommitsByMonth, ReportsCommitsByMonth
from cauldron_apps.cauldron_actions.models import IRefreshActions
from cauldron_apps.poolsched_sbom.models import SPDXUserFile, IParseSPDX
from cauldron_apps.cauldron.models import IAddGHOwner, IAddGLOwner, Project, OauthUser, AnonymousUser, \
    UserWorkspace, Repository, GitLabRepository, GitRepository, GitHubRepository, MeetupRepository, \
    StackExchangeRepository, AuthorizedBackendUser, BannerMessage, RepositoryMetrics

from cauldron_apps.cauldron.opendistro import OpendistroApi

import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

User = get_user_model()

JOB_LOGS = '/job_logs'

ES_IN_URL = "{}://{}:{}".format(settings.ES_IN_PROTO, settings.ES_IN_HOST, settings.ES_IN_PORT)
KIB_IN_URL = "{}://{}:{}{}".format(settings.KIB_IN_PROTO, settings.KIB_IN_HOST, settings.KIB_IN_PORT, settings.KIB_PATH)

logger = logging.getLogger(__name__)


def homepage(request):
    # If user is authenticated, homepage is My projects page
    if request.user.is_authenticated:
        return request_user_projects(request)

    # If LIMITED_ACCESS is enabled, show explore page
    if settings.LIMITED_ACCESS:
        return HttpResponseRedirect(reverse('explore_projects'))

    latest_projects = Project.objects.order_by('-created')[:6]

    context = create_context(request)
    context['latest_projects'] = latest_projects

    return render(request, 'cauldronapp/index.html', context=context)


def request_user_projects(request):
    if not request.user.is_authenticated:
        context = create_context(request)
        context['title'] = "You are not logged in"
        context['description'] = "You need to login or create a new report to continue"
        return render(request, 'cauldronapp/error.html', status=400, context=context)
    projects = Project.objects.filter(creator=request.user)
    return request_projects(request, projects)


def request_explore_projects(request):
    projects = Project.objects.all()
    if not request.user.is_authenticated:
        projects = projects.filter(public=True)
    return request_projects(request, projects)


def request_projects(request, projects):
    context = create_context(request)
    search = request.GET.get('search')
    if search is not None:
        projects = projects.filter(name__icontains=search)
    projects, sort_by = sort_reports(request, projects)
    context['sort_by'] = sort_by
    p = Pages(projects, 9)
    page_number = request.GET.get('page', 1)
    page_obj = p.pages.get_page(page_number)
    context['page_obj'] = page_obj
    context['pages_to_show'] = p.pages_to_show(page_obj.number)

    projects_info = list()
    for project in page_obj.object_list:
        summary = project.summary()
        summary['project'] = project
        summary['metrics'] = metrics.report_card_metrics(project, summary)
        projects_info.append(summary)
    context['projects_info'] = projects_info
    if request.user.is_authenticated:
        context['total_projects'] = Project.objects.count()
    else:
        context['total_projects'] = Project.objects.filter(public=True).count()
    if request.user.is_authenticated:
        context['user_projects'] = Project.objects.filter(creator=request.user).count()
    return render(request, 'cauldronapp/projects/projects.html', context=context)


def sort_reports(request, projects):
    sort_names = {
        'name_asc': 'Name',
        'name_desc': 'Name, descending',
        'last_created': 'Last created',
        'oldest_created': 'Oldest created',
        'last_updated': 'Last updated',
        'oldest_updated': 'Oldest updated',
    }
    simple_sort_filters = {
        'name_asc': 'name',
        'name_desc': '-name',
        'last_created': '-created',
        'oldest_created': 'created'
    }
    default = request.session.get('reports_sort', 'last_created')
    key = request.GET.get('sort', default)
    if key not in sort_names:
        key = 'last_created'
    request.session['reports_sort'] = key

    if key in simple_sort_filters:
        projects = projects.order_by(simple_sort_filters[key])
    elif key == 'last_updated':
        projects = projects.annotate(refresh_date=Min('repository__last_refresh')).order_by('-refresh_date')
    elif key == 'oldest_updated':
        projects = projects.annotate(refresh_date=Min('repository__last_refresh')).order_by('refresh_date')

    return projects, {'key': key, 'name': sort_names[key]}


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
    new_project_info = request.session.get('new_project')
    store_oauth = request.session.get('store_oauth')

    merged, allowed = authenticate_user(request, 'github', oauth_user, is_admin)
    if not allowed:
        return custom_403(request, "You are not allowed to authenticate in this server. "
                                   "Ask any of the administrators for permission.")

    if merged:
        request.session['alert_notification'] = {'title': 'Account merged',
                                                 'message': f"You already had a Cauldron user with this GitHub account."
                                                            f" We have proceeded to merge all the reports and "
                                                            f"visualization in you current account so that you do not "
                                                            f"loose anything"}
    GHToken.objects.update_or_create(user=request.user, defaults={'token': oauth_user.token})

    if data_add and data_add['backend'] == 'github':
        project = Project.objects.filter(id=data_add['proj_id']).first()
        datasources.github.analyze_data(project,
                                        data_add['data'], data_add['commits'],
                                        data_add['issues'], data_add['forks'])

    request.session['new_project'] = new_project_info
    request.session['store_oauth'] = store_oauth

    if last_page:
        return HttpResponseRedirect(last_page)

    return HttpResponseRedirect(reverse('homepage'))


def merge_accounts(user_origin, user_dest):
    """Change the references of that user to another one"""
    OauthUser.objects.filter(user=user_origin).update(user=user_dest)
    Project.objects.filter(creator=user_origin).update(creator=user_dest)
    GHToken.objects.filter(user=user_origin).update(user=user_dest)
    GLToken.objects.filter(user=user_origin).update(user=user_dest)
    MeetupToken.objects.filter(user=user_origin).update(user=user_dest)
    StackExchangeToken.objects.filter(user=user_origin).update(user=user_dest)
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
    obj = kibana_objects.export_all_objects(KIB_IN_URL, settings.ES_ADMIN_PASSWORD, old_user.userworkspace.tenant_name)
    kibana_objects.import_object(KIB_IN_URL, settings.ES_ADMIN_PASSWORD, obj, new_user.userworkspace.tenant_name)


# TODO: Add state
def request_gitlab_oauth(request, backend):
    redirect_uri = request.build_absolute_uri()
    code = request.GET.get('code', None)
    if not code:
        return custom_404(request, "Code not found in the GitLab callback")
    try:
        instance = GLInstance.objects.get(slug=backend)
    except GLInstance.DoesNotExist:
        return custom_404(request, f"Backend '{backend}' does not exist in this server")
    gitlab = GitLabOAuth(instance, redirect_uri)
    error = gitlab.authenticate(code)
    if error:
        return custom_500(request, error)
    oauth_user = gitlab.user_data()
    is_admin = oauth_user.username in settings.CAULDRON_ADMINS.get(backend.upper(), [])

    # Save the state of the session
    data_add = request.session.pop('add_repo', None)
    last_page = request.session.pop('last_page', None)
    new_project_info = request.session.get('new_project')
    store_oauth = request.session.get('store_oauth')

    merged, allowed = authenticate_user(request, backend, oauth_user, is_admin)
    if not allowed:
        return custom_403(request, "You are not allowed to authenticate in this server. "
                                   "Ask any of the administrators for permission.")

    if merged:
        request.session['alert_notification'] = {'title': 'Account merged',
                                                 'message': f"You already had a Cauldron user with this GitLab account."
                                                            f" We have proceeded to merge all the reports and "
                                                            f"visualization in you current account so that you do not "
                                                            f"loose anything"}

    GLToken.objects.update_or_create(user=request.user, instance=instance, defaults={'token': oauth_user.token})

    if data_add and data_add['backend'] == backend:
        project = Project.objects.get(id=data_add['proj_id'])
        datasources.gitlab.analyze_data(project,
                                        data_add['data'], data_add['commits'],
                                        data_add['issues'], data_add['forks'],
                                        instance=instance)

    request.session['new_project'] = new_project_info
    request.session['store_oauth'] = store_oauth

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
    redirect_uri = request.build_absolute_uri(reverse('meetup_callback'))
    meetup = MeetupOAuth(settings.MEETUP_CLIENT_ID, settings.MEETUP_CLIENT_SECRET, redirect_uri)
    error = meetup.authenticate(code)
    if error:
        return custom_500(request, error)
    oauth_user = meetup.user_data()

    is_admin = oauth_user.username in settings.CAULDRON_ADMINS['MEETUP']

    # Save the state of the session
    data_add = request.session.pop('add_repo', None)
    last_page = request.session.pop('last_page', None)
    new_project_info = request.session.get('new_project')
    store_oauth = request.session.get('store_oauth')

    merged, allowed = authenticate_user(request, 'meetup', oauth_user, is_admin)
    if not allowed:
        return custom_403(request, "You are not allowed to authenticate in this server. "
                                   "Ask any of the administrators for permission.")

    if merged:
        request.session['alert_notification'] = {'title': 'Account merged',
                                                 'message': f"You already had a Cauldron user with this Meetup account."
                                                            f" We have proceeded to merge all the reports and "
                                                            f"visualization in you current account so that you do not "
                                                            f"loose anything"}

    MeetupToken.objects.update_or_create(user=request.user, defaults={'token': oauth_user.token,
                                                                      'refresh_token': oauth_user.refresh_token})

    if data_add and data_add['backend'] == 'meetup':
        project = Project.objects.get(id=data_add['proj_id'])
        datasources.meetup.analyze_data(project, data_add['data'])

    request.session['new_project'] = new_project_info
    request.session['store_oauth'] = store_oauth

    if last_page:
        return HttpResponseRedirect(last_page)

    return HttpResponseRedirect(reverse('homepage'))


# TODO: Add state
def request_twitter_oauth(request):
    error = request.GET.get('error', None)
    if error:
        return custom_404(request, f"Twitter callback error. {error}")

    oauth_token = request.GET.get('oauth_token', None)
    if not oauth_token:
        return custom_404(request, "OAuth Token not found in the Twitter callback")

    oauth_verifier = request.GET.get('oauth_verifier', None)
    if not oauth_verifier:
        return custom_404(request, "OAuth Verifier not found in the Twitter callback")

    redirect_uri = request.build_absolute_uri(reverse('twitter_callback'))
    twitter = TwitterOAuth(settings.TWITTER_CLIENT_ID, settings.TWITTER_CLIENT_SECRET, redirect_uri)
    error = twitter.authenticate(oauth_token, oauth_verifier)
    if error:
        return custom_500(request, error)
    oauth_user = twitter.user_data()

    is_admin = oauth_user.username in settings.CAULDRON_ADMINS['TWITTER']

    # Save the state of the session
    last_page = request.session.pop('last_page', None)
    new_project_info = request.session.get('new_project')
    store_oauth = request.session.get('store_oauth')

    merged, allowed = authenticate_user(request, 'twitter', oauth_user, is_admin)
    if not allowed:
        return custom_403(request, "You are not allowed to authenticate in this server. "
                                   "Ask any of the administrators for permission.")

    if merged:
        request.session['alert_notification'] = {'title': 'Account merged',
                                                 'message': f"You already had a Cauldron user with this Twitter account. "
                                                            f"We have proceeded to merge all the reports and "
                                                            f"visualization in you current account so that you do not "
                                                            f"loose anything"}

    request.session['new_project'] = new_project_info
    request.session['store_oauth'] = store_oauth

    if last_page:
        return HttpResponseRedirect(last_page)

    return HttpResponseRedirect(reverse('homepage'))


# TODO: Add state
def request_stack_oauth(request):
    error = request.GET.get('error', None)
    if error:
        return custom_404(request, f"StackExchange callback error. {error}")
    code = request.GET.get('code', None)
    if not code:
        return custom_404(request, "Code not found in the StackExchange callback")
    redirect_uri = request.build_absolute_uri(reverse('stackexchange_callback'))
    stack = StackExchangeOAuth(settings.STACK_EXCHANGE_CLIENT_ID, settings.STACK_EXCHANGE_CLIENT_SECRET,
                               settings.STACK_EXCHANGE_APP_KEY, redirect_uri)
    error = stack.authenticate(code)
    if error:
        return custom_500(request, error)
    oauth_user = stack.user_data()
    if not oauth_user:
        return custom_500(request, 'User not found for your token')

    is_admin = oauth_user.username in settings.CAULDRON_ADMINS['STACK_EXCHANGE']

    # Save the state of the session
    data_add = request.session.pop('add_repo', None)
    last_page = request.session.pop('last_page', None)
    new_project_info = request.session.get('new_project')
    store_oauth = request.session.get('store_oauth')

    merged, allowed = authenticate_user(request, 'stackexchange', oauth_user, is_admin)
    if not allowed:
        return custom_403(request, "You are not allowed to authenticate in this server. "
                                   "Ask any of the administrators for permission.")

    if merged:
        request.session['alert_notification'] = {'title': 'Account merged',
                                                 'message': f"You already had a Cauldron user with this StackExchange account."
                                                            f" We have proceeded to merge all the projects and "
                                                            f"visualization in you current account so that you do not "
                                                            f"loose anything"}

    StackExchangeToken.objects.update_or_create(user=request.user, defaults={'token': oauth_user.token,
                                                                             'api_key': settings.STACK_EXCHANGE_APP_KEY})

    if data_add and data_add['backend'] == 'stackexchange':
        project = Project.objects.get(id=data_add['proj_id'])
        datasources.stackexchange.analyze_data(project, data_add['site'], data_add['tag'])

    request.session['new_project'] = new_project_info
    request.session['store_oauth'] = store_oauth

    if last_page:
        return HttpResponseRedirect(last_page)

    return HttpResponseRedirect(reverse('homepage'))


def authenticate_user(request, backend, oauth_info, is_admin=False):
    """
    Authenticate an oauth request and merge with existent accounts if needed
    :param request: request from login callback
    :param backend: git, github, gitlab...
    :param oauth_info: user information obtained from the backend
    :param is_admin: flag to indicate that the user to authenticate is an admin
    :return: boolean, boolean. The user has been merged, the user is allowed to authenticate
    """
    if (settings.LIMITED_ACCESS and
            not request.user.is_authenticated and
            not is_admin and
            not AuthorizedBackendUser.objects.filter(backend=backend, username=oauth_info.username).exists()):
        return False, False

    merged, allowed = False, True
    try:
        existing_oauth_user = OauthUser.objects.get(backend=backend, username=oauth_info.username)
        backend_user = existing_oauth_user.user
    except OauthUser.DoesNotExist:
        backend_user = None

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
                request.user.first_name = oauth_info.name
                request.user.save()

        else:
            # No one is authenticated and backend user doesn't exist
            # Create account
            dj_user = create_django_user(oauth_info.name)
            login(request, dj_user)

        # Create the backend entity and associate with the account
        OauthUser.objects.create(user=request.user,
                                 backend=backend,
                                 username=oauth_info.username,
                                 photo=oauth_info.photo)

    # If it is an admin user, upgrade it
    if is_admin:
        upgrade_to_admin(request.user)

    return merged, allowed


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


def request_login(request):
    context = create_context(request)

    return render(request, 'cauldronapp/login.html', context=context)


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
    context['sidebar'] = True
    context['project'] = project
    context['repositories_count'] = project.repository_set.count()
    context['has_git'] = GitRepository.objects.filter(projects=project).exists()
    context['active_notifications'] = ITwitterNotify.objects.filter(project=project).exists()
    context['editable'] = ((request.user.is_authenticated and request.user == project.creator) or
                           request.user.is_superuser)
    context['autorefresh_enabled'] = settings.AUTOREFRESH_ENABLED
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

    sort_by = request.GET.get('sort_by', 'id')
    if sort_by[0] == '-':
        reverse = True
        sort_by = sort_by[1:]
    else:
        reverse = False
    if sort_by not in ('name', 'commits', 'issues', 'reviews', 'commits_authors',
                       'issues_submitters', 'reviews_submitters'):
        sort_by = 'id'

    page_number = request.GET.get('page')

    if settings.HATSTALL_ENABLED:
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

        urls = request.GET.getlist('repo_url[]')
        if not urls:
            urls = project.url_list()

        elastic = metrics.get_elastic_project(project)
        contrib_metrics = metrics.people_commits.contributors_and_affiliations(elastic=elastic,
                                                                               urls=urls,
                                                                               from_date=from_date,
                                                                               to_date=to_date)

        context['contributors'] = contrib_metrics

    repo_metrics = RepositoryMetrics.objects.filter(repository__in=project.repository_set.all()) \
        .distinct() \
        .order_by(sort_by)
    if reverse:
        repo_metrics = repo_metrics.reverse()
    p = Pages(repo_metrics, 20)
    page_obj = p.pages.get_page(page_number)
    context['page_obj'] = page_obj
    context['pages_to_show'] = p.pages_to_show(page_obj.number)

    context['show_project_home'] = True
    context['has_git'] = GitRepository.objects.filter(projects=project).exists()
    context['has_github'] = GitHubRepository.objects.filter(projects=project).exists()
    context['has_gitlab'] = GitLabRepository.objects.filter(projects=project).exists()
    context['has_meetup'] = MeetupRepository.objects.filter(projects=project).exists()
    context['has_stack'] = StackExchangeRepository.objects.filter(projects=project).exists()
    context['hatstall_enabled'] = settings.HATSTALL_ENABLED
    context['repos'] = project.repository_set.all().select_subclasses()

    return render(request, 'cauldronapp/project/project.html', context=context)


def request_project_repositories(request, project_id):
    """ View for the repositories of a project"""
    if request.method != 'GET':
        return custom_405(request, request.method)

    try:
        project, context = project_common(request, project_id)
    except Project.DoesNotExist:
        return custom_404(request, "The report requested was not found in this server")

    context['show_table'] = True
    repositories = project.repository_set.all()
    p = Pages(repositories.select_subclasses(), 10)
    page_number = request.GET.get('page', 1)
    page_obj = p.pages.get_page(page_number)
    context['page_obj'] = page_obj
    context['pages_to_show'] = p.pages_to_show(page_obj.number)

    return render(request, 'cauldronapp/project/project.html', context=context)


def request_project_actions(request, project_id):
    """Render a view for all the actions for a project"""
    try:
        project, context = project_common(request, project_id)
    except Project.DoesNotExist:
        return custom_404(request, "The report requested was not found in this server")

    context['public'] = project.public
    context['show_actions'] = True
    context['actions'] = project.action_set.select_subclasses()

    return render(request, 'cauldronapp/project/project.html', context=context)


@require_http_methods(['POST'])
def request_report_visibility(request, project_id):
    if not request.user.is_authenticated:
        return JsonResponse({'message': 'You are not authenticated', 'status': 402})
    try:
        project = Project.objects.get(pk=project_id)
    except Project.DoesNotExist:
        return JsonResponse({'message': 'The report requested was not found in this server', 'status': 404})

    if not request.user.is_authenticated or (request.user != project.creator and not request.user.is_superuser):
        return JsonResponse({'message': 'You are not allowed to modify this report', 'status': 404})

    visibility = request.POST.get('visibility')
    if visibility in ('public', 'private'):
        project.public = True if visibility == 'public' else False
        project.save()

    status = 'public' if project.public else 'private'
    return JsonResponse({'message': f'Your project is now {status}', 'status': 'Success'})


def request_project_actions_refresh(request, project_id):
    if request.method != 'POST':
        return custom_405(request, request.method)
    try:
        project = Project.objects.get(pk=project_id)
    except Project.DoesNotExist:
        return custom_404(request, "The report requested was not found in this server")

    if not request.user.is_authenticated and request.user != project.creator and not request.user.is_superuser:
        return custom_403(request)

    IRefreshActions.objects.create(user=project.creator, project=project)

    return HttpResponseRedirect(reverse('show_project_actions', kwargs={'project_id': project.id}))


def request_project_actions_remove(request, project_id):
    try:
        project = Project.objects.get(pk=project_id)
    except Project.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Report not found'}, status=404)

    if not request.user.is_authenticated and request.user != project.creator and not request.user.is_superuser:
        return JsonResponse({'status': 'error', 'message': 'Unauthorized'}, status=403)

    action_id = request.POST.get('action_id', None)
    if action_id is None:
        return JsonResponse({'status': 'error', 'message': 'action_id not defined'}, status=404)

    project.action_set.filter(id=action_id).delete()
    return JsonResponse({'status': 'ok'})


def request_repo_intentions(request, repo_id):
    """View for a repository. It shows all the intentions related"""
    context = create_context(request)
    try:
        repo = Repository.objects.get_subclass(id=repo_id)
    except Repository.DoesNotExist:
        return custom_404(request, 'Repository not found in this server')

    context['repo'] = repo
    context['intentions'] = repo.get_intentions()

    return render(request, 'cauldronapp/project/repo_actions.html', context=context)


def request_dismiss_message(request, message_id):
    if not request.user.is_authenticated:
        return JsonResponse({'message': 'You are not authenticated', 'status': 402})
    try:
        message = BannerMessage.objects.get(id=message_id)
    except BannerMessage.DoesNotExist:
        return JsonResponse({'message': "You can't dismiss a message that doesn't exist", 'status': 404})
    message.read_by.add(request.user)
    return JsonResponse({'message': f"Message {message_id} dismissed"})


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


def request_spdx_results(request, spdx_id):
    try:
        dbfile = SPDXUserFile.objects.get(id=spdx_id)
    except SPDXUserFile.DoesNotExist:
        return JsonResponse({'error': "SPDX file not found."})
    if not dbfile.result:
        return JsonResponse({'status': 'parsing'})
    if 'results' in dbfile.result:
        return JsonResponse(dbfile.result)


def create_repositories(project, repositories):
    """
    Repositories should include at least the backend name. For each backend different parameters are needed.
    GitHub: backend, url, Commits?, Issues/PRs?, Forks?
    GitLab: backend, url, instance?, Commits?, Issues/MRs?, Forks?
    Git: backend, url
    Meetup: backend, url
    StackExchange: backend, site, tags
    """
    error = None

    for repo_url in repositories:
        owner, repo = datasources.github.parse_input_data(repo_url)
        if owner and repo:
            if not project.creator.ghtokens.filter(instance='GitHub').exists():
                error = 'Missing GitHub token for a repository'
                break
            commits, issues, forks = True, True, False
            output = datasources.github.analyze_data(project=project,
                                                     data=repo_url,
                                                     commits=commits,
                                                     issues=issues,
                                                     forks=forks)
            if output and output['status'] != 'ok':
                error = output['message']
                break

        gl_instance = GLInstance.objects.get(slug='gitlab')
        owner, repo = datasources.gitlab.parse_input_data(repo_url, gl_instance.endpoint)
        if owner and repo:
            if not project.creator.gltokens.filter(instance=gl_instance).exists():
                error = 'Missing GitLab token for a repository'
                break
            commits, issues, forks = True, True, False
            output = datasources.gitlab.analyze_data(project=project,
                                                     data=repo_url,
                                                     instance=gl_instance,
                                                     commits=commits,
                                                     issues=issues,
                                                     forks=forks)
            if output and output['status'] != 'ok':
                error = output['message']
                break

    return error


def request_create_sbom(request):
    data = request.session.get('new_project')
    if data is None:
        data = {}

    if request.method == 'POST':
        if 'name' in request.POST:
            data['name'] = request.POST['name']
            request.session['new_project'] = data
            if request.user.is_authenticated and \
                    Project.objects.filter(creator=request.user, name=data['name']).exists():
                return JsonResponse({'status': 'error', 'message': 'You have the same name defined in another report'})
            elif len(data['name']) < 1 or len(data['name']) > 32:
                return JsonResponse({'status': 'error', 'message': 'Must be 1-32 characters long.'})
            return JsonResponse({'status': 'ok'}, status=200)

        if 'create' in request.POST and 'repository' in request.POST:
            repositories = request.POST.getlist('repository')
            error = _validate_data_project(request, data)
            if error:
                return custom_404(request, error)
            if not request.user.is_authenticated:
                if not settings.LIMITED_ACCESS:
                    user = create_empty_user()
                    login(request, user)
                else:
                    return custom_404(request, 'Not authorized')
            public = False if settings.LIMITED_ACCESS else True
            project = Project.objects.create(name=data['name'], creator=request.user, public=public)
            project.create_es_role()
            error = create_repositories(project, repositories)
            if error:
                delete_project(project)
                return custom_403(request, error)
            del request.session['new_project']
            return HttpResponseRedirect(reverse('show_project', kwargs={'project_id': project.id}))

        if 'spdx_file' in request.FILES:
            spdx_file = request.FILES['spdx_file']
            dbfile = SPDXUserFile.objects.create(uploaded_by=request.user, name=spdx_file.name)
            file_path = os.path.join(settings.SPDX_FILES_PATH, dbfile.location)
            with open(file_path, 'wb+') as destination:
                for chunk in spdx_file.chunks():
                    destination.write(chunk)
            IParseSPDX.objects.create(user=request.user, spdx_file=dbfile)
            data['spdx_file'] = dbfile.id
            request.session['new_project'] = data

    context = create_context(request)

    if request.user.is_authenticated:
        context['github_enabled'] = request.user.ghtokens.filter(instance='GitHub').exists()
        context['gitlab_enabled'] = request.user.gltokens.filter(instance='GitLab').exists()

    context['new_project'] = request.session.get('new_project')

    request.session['last_page'] = reverse('create_sbom')
    return render(request, 'cauldronapp/create_sbom/base.html', context=context)


@require_http_methods(['POST'])
def request_add_to_project(request, project_id):
    """ Add new repositories to a project"""
    project = Project.objects.filter(id=project_id).first()
    if not project:
        return JsonResponse({'status': 'error', 'message': 'Report not found'}, status=404)
    if not request.user.is_authenticated or (request.user != project.creator and not request.user.is_superuser):
        return JsonResponse({'status': 'error', 'message': 'You cannot edit this project'}, status=403)

    backend = request.POST.get('backend', None)

    if backend == 'git':
        data = request.POST.get('data', None)
        if not data:
            return JsonResponse({'status': 'error', 'message': 'URL to analyze missing'}, status=400)
        data = data.strip()
        datasources.git.analyze_git(project, data)
        project.update_elastic_role()
        return JsonResponse({'status': 'ok'})

    elif backend == 'github':
        data = request.POST.get('data', None)
        if not data:
            return JsonResponse({'status': 'error', 'message': 'URL/Owner to analyze missing'}, status=400)
        analyze_commits = 'commits' in request.POST
        analyze_issues = 'issues' in request.POST
        forks = 'forks' in request.POST
        if not request.user.ghtokens.filter(instance='GitHub').exists():
            request.session['add_repo'] = {'data': data,
                                           'backend': backend,
                                           'proj_id': project.id,
                                           'commits': analyze_commits,
                                           'forks': forks,
                                           'issues': analyze_issues}
            request.session['last_page'] = reverse('show_project', kwargs={'project_id': project.id})
            return JsonResponse({'status': 'error',
                                 'message': generate_request_token_message("GitHub"),
                                 'redirect': reverse('github_oauth')},
                                status=401)
        output = datasources.github.analyze_data(project=project, data=data, commits=analyze_commits,
                                                 issues=analyze_issues, forks=forks)

        return JsonResponse(output, status=output['code'])

    elif backend == 'meetup':
        data = request.POST.get('data', None)
        if not data:
            return JsonResponse({'status': 'error', 'message': 'Group to analyze missing'}, status=400)
        if not request.user.meetuptokens.exists():
            request.session['add_repo'] = {'data': data, 'backend': backend, 'proj_id': project.id}
            request.session['last_page'] = reverse('show_project', kwargs={'project_id': project.id})
            return JsonResponse({'status': 'error',
                                 'message': generate_request_token_message("Meetup"),
                                 'redirect': reverse('meetup_oauth')},
                                status=401)

        output = datasources.meetup.analyze_data(project=project, data=data)
        return JsonResponse(output, status=output['code'])

    elif backend == 'stackexchange':
        tagged = request.POST.get('tagged', None)
        site = request.POST.get('site', None)
        if not site or not tagged:
            return JsonResponse({'status': 'error', 'message': 'Site or tag missing'}, status=400)
        if not project.creator.stackexchangetokens.exists():
            if request.user != project.creator:
                return JsonResponse({'status': 'error',
                                     'message': 'Project owner needs a StackExchange token to'
                                                ' analyze this kind of repositories'},
                                    status=401)
            request.session['add_repo'] = {'backend': backend, 'site': site, 'tag': tagged, 'proj_id': project.id}
            request.session['last_page'] = reverse('show_project', kwargs={'project_id': project.id})
            return JsonResponse({'status': 'error',
                                 'message': generate_request_token_message("StackExchange"),
                                 'redirect': reverse('stack_oauth')},
                                status=401)

        output = datasources.stackexchange.analyze_data(project, site, tagged)
        return JsonResponse(output, status=output['code'])

    gl_instance = GLInstance.objects.filter(slug=backend).first()
    if gl_instance:
        data = request.POST.get('data', None)
        analyze_commits = 'commits' in request.POST
        analyze_issues = 'issues' in request.POST
        forks = 'forks' in request.POST
        instance = GLInstance.objects.get(slug=backend)
        if not request.user.gltokens.filter(instance__slug=backend).exists():
            request.session['add_repo'] = {'data': data,
                                           'backend': backend,
                                           'proj_id': project.id,
                                           'commits': analyze_commits,
                                           'forks': forks,
                                           'issues': analyze_issues}
            request.session['last_page'] = reverse('show_project', kwargs={'project_id': project.id})
            return JsonResponse({'status': 'error',
                                 'message': generate_request_token_message(instance.name),
                                 'redirect': reverse('gitlab_oauth', kwargs={'backend': backend})},
                                status=401)
        output = datasources.gitlab.analyze_data(project=project, data=data, commits=analyze_commits,
                                                 issues=analyze_issues, forks=forks, instance=instance)
        return JsonResponse(output, status=output['code'])

    return JsonResponse({'status': 'error', 'message': f'Backend {backend} not found'}, status=400)


@require_http_methods(["POST"])
def request_remove_from_project(request, project_id):
    project = Project.objects.filter(id=project_id).first()
    if not project:
        return JsonResponse({'status': 'error', 'message': 'Report not found'}, status=404)
    if not request.user.is_authenticated or (request.user != project.creator and not request.user.is_superuser):
        return JsonResponse({'status': 'error', 'message': 'You cannot edit this report'}, status=403)

    repo_id = request.POST.get('repository', None)

    if not repo_id:
        return JsonResponse({'status': 'error', 'message': 'We need a url to delete'},
                            status=400)

    if repo_id == 'all':
        for repo in project.repository_set.select_subclasses():
            repo.remove_intentions(request.user)
        project.action_set.all().delete()
        project.repository_set.clear()
        project.update_elastic_role()
    else:
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
        return JsonResponse({'status': 'error', 'message': f"Report {project_id} does not exist"},
                            status=404)
    if not (request.user.is_authenticated and (request.user == project.creator or request.user.is_superuser)):
        return JsonResponse({'status': 'error', 'message': f'You cannot edit report {project_id}, '
                                                           f'you are not the owner'},
                            status=400)

    name = request.POST.get('name', '').strip()

    if len(name) < 1 or len(name) > 32:
        return JsonResponse({'status': 'error', 'message': "The name doesn't fit the allowed length "},
                            status=400)

    if Project.objects.filter(creator=project.creator, name=name).exclude(id=project_id).exists():
        return JsonResponse({'status': 'Duplicated name', 'message': 'You have the same name in another report'},
                            status=400)
    project.name = name
    project.save()
    return JsonResponse({'status': 'Ok', 'message': 'Name updated successfully'})


def create_project(request):
    error = None
    if request.method == 'POST':
        if 'name' in request.POST:
            data = request.session.get('new_project')
            if data is None:
                data = {}
            data['name'] = request.POST['name']
            request.session['new_project'] = data
            if request.user.is_authenticated and \
                    Project.objects.filter(creator=request.user, name=data['name']).exists():
                return JsonResponse({'status': 'error', 'message': 'You have the same name defined in another report'})
            elif len(data['name']) < 1 or len(data['name']) > 32:
                return JsonResponse({'status': 'error', 'message': 'Must be 1-32 characters long.'})
            return JsonResponse({'status': 'ok'}, status=200)

        elif 'add' in request.POST:
            error = create_project_add(request)

        elif 'delete' in request.POST:
            error = create_project_delete(request)

        elif 'create' in request.POST:
            return request_new_project(request)

    context = create_context(request)
    context['error_message'] = error.get('message', None) if error else None
    store_oauth = request.session.get('store_oauth')
    if store_oauth:
        context['open_tab'] = store_oauth.get('open_tab')
        del request.session['store_oauth']
    if request.user.is_authenticated:
        context['github_enabled'] = request.user.ghtokens.filter(instance='GitHub').exists()
        context['gitlab_enabled'] = request.user.gltokens.filter(instance='GitLab').exists()
        context['gnome_enabled'] = request.user.gltokens.filter(instance='Gnome').exists()
        context['kde_enabled'] = request.user.gltokens.filter(instance='KDE').exists()
        context['meetup_enabled'] = request.user.meetuptokens.exists()
        context['stack_enabled'] = request.user.stackexchangetokens.exists()
        context['twitter_enabled'] = OauthUser.objects.filter(user=request.user, backend='twitter').exists()

    context['new_project'] = request.session.get('new_project')

    request.session['last_page'] = reverse('create_project')
    return render(request, 'cauldronapp/create_project/base.html', context=context)


def random_id(size):
    return ''.join(random.choice(ascii_lowercase) for _ in range(size))


def create_project_add(request):
    backend = request.POST.get('backend')
    if backend == 'git':
        data = request.POST.get('data')
        if not data:
            return {'status': 'error', 'message': 'URL not found for Git repository'}
        data = data.strip()

        data_project = request.session.get('new_project')
        if data_project is None:
            data_project = {}
        if 'actions' not in data_project:
            data_project['actions'] = []
        data_project['actions'].append({'id': random_id(5), 'backend': 'git', 'data': data, 'attrs': {'Commits': True}})
        request.session['new_project'] = data_project

    elif backend == 'github':
        data = request.POST.get('data')
        if not data:
            return {'status': 'error', 'message': 'No data entered to add'}
        if not request.user.is_authenticated or not request.user.ghtokens.filter(instance='GitHub').exists():
            return {'status': 'error', 'message': 'User requesting this data is not authenticated for GitHub. '
                                                  'Please, refresh the page.'}
        commits = 'commits' in request.POST
        issues = 'issues' in request.POST
        forks = 'forks' in request.POST
        data_owner, data_repo = datasources.github.parse_input_data(data)
        if data_owner and data_repo:
            data_store = f'{data_owner}/{data_repo}'
            attrs_store = {'Commits': commits, 'Issues/PRs': issues}
        elif data_owner:
            data_store = data_owner
            attrs_store = {'Commits': commits, 'Issues/PRs': issues, 'Forks': forks}
        else:
            return {'status': 'error', 'message': f"We can't guess what do you mean with '{data}'"}

        data_project = request.session.get('new_project')
        if data_project is None:
            data_project = {}
        if 'actions' not in data_project:
            data_project['actions'] = []
        data_project['actions'].append({'id': random_id(5), 'backend': 'github',
                                        'data': data_store, 'attrs': attrs_store})
        request.session['new_project'] = data_project

    elif backend == 'gitlab':
        data = request.POST.get('data')
        instance = request.POST.get('instance')
        if not data or not instance:
            return {'status': 'error', 'message': 'No data entered to add'}
        if not request.user.is_authenticated or not request.user.gltokens.filter(instance__slug=instance).exists():
            return {'status': 'error', 'message': 'User requesting this data is not authenticated for GitLab. '
                                                  'Please, refresh the page.'}
        commits = 'commits' in request.POST
        issues = 'issues' in request.POST
        forks = 'forks' in request.POST
        instance_obj = GLInstance.objects.get(slug=instance)
        data_owner, data_repo = datasources.gitlab.parse_input_data(data, instance_obj.endpoint)
        if data_owner and data_repo:
            data_store = f'{data_owner}/{data_repo}'
            attrs_store = {'Commits': commits, 'Issues/MRs': issues}
        elif data_owner:
            data_store = data_owner
            attrs_store = {'Commits': commits, 'Issues/MRs': issues, 'Forks': forks}
        else:
            return {'status': 'error', 'message': f"We can't guess what do you mean with '{data}'"}

        data_project = request.session.get('new_project')
        if data_project is None:
            data_project = {}
        if 'actions' not in data_project:
            data_project['actions'] = []
        data_project['actions'].append({'id': random_id(5), 'backend': 'gitlab', 'instance': instance,
                                        'data': data_store, 'attrs': attrs_store})
        request.session['new_project'] = data_project

    elif backend == 'meetup':
        data = request.POST.get('data')
        if not data:
            return {'status': 'error', 'message': 'No data entered to add'}
        if not request.user.is_authenticated or not request.user.meetuptokens.exists():
            return {'status': 'error', 'message': 'User requesting this data is not authenticated for Meetup. '
                                                  'Please, refresh the page.'}

        group = datasources.meetup.parse_input_data(data)
        if not group:
            return {'status': 'error', 'message': f"We can't guess what do you mean with '{data}'"}

        data_project = request.session.get('new_project')
        if data_project is None:
            data_project = {}
        if 'actions' not in data_project:
            data_project['actions'] = []
        data_project['actions'].append({'id': random_id(5), 'backend': 'meetup',
                                        'data': group, 'attrs': {'Events': True}})
        request.session['new_project'] = data_project

    elif backend == 'stackexchange':
        tagged = request.POST.get('tagged', None)
        site = request.POST.get('site', None)

        if not tagged:
            return {'status': 'error', 'message': 'No tags defined'}
        if not site:
            return {'status': 'error', 'message': 'No site defined'}
        if not request.user.is_authenticated or not request.user.stackexchangetokens.exists():
            return {'status': 'error', 'message': 'User requesting this data is not authenticated for StackExchange. '
                                                  'Please, refresh the page.'}

        tags = datasources.stackexchange.parse_tags(tagged)
        if not tags:
            return {'status': 'error', 'message': f"We can't guess what do you mean with '{tagged}'"}

        data_project = request.session.get('new_project')
        if data_project is None:
            data_project = {}
        if 'actions' not in data_project:
            data_project['actions'] = []
        data_project['actions'].append({'id': random_id(5), 'backend': 'stackexchange',
                                        'data': f'{site}: {tags}', 'attrs': {'questions': True},
                                        'params': {'site': site, 'tags': tags}})
        request.session['new_project'] = data_project

    elif backend == 'repo_list':
        data = []

        list_data = request.POST.get('list_data')
        if list_data:
            data.extend(list_data.splitlines())

        repo_file = request.FILES.get('repo_file')
        if repo_file:
            for chunk in repo_file.chunks():
                data.extend(chunk.splitlines())

        if not data:
            return {'status': 'error', 'message': 'No data entered to add'}

        error = False
        gitlab_instance = GLInstance.objects.get(slug='gitlab')

        for repo_url in data:
            if isinstance(repo_url, bytes):
                repo_url = repo_url.decode()

            if datasources.github.parse_input_data(repo_url) != (None, None):
                if not request.user.is_authenticated or not request.user.ghtokens.filter(instance='GitHub').exists():
                    error = True
                    continue

                commits = True
                issues = True
                forks = False
                data_owner, data_repo = datasources.github.parse_input_data(repo_url)
                if data_owner and data_repo:
                    data_store = f'{data_owner}/{data_repo}'
                    attrs_store = {'Commits': commits, 'Issues/PRs': issues}
                elif data_owner:
                    data_store = data_owner
                    attrs_store = {'Commits': commits, 'Issues/PRs': issues, 'Forks': forks}
                else:
                    error = True
                    continue

                data_project = request.session.get('new_project')
                if data_project is None:
                    data_project = {}
                if 'actions' not in data_project:
                    data_project['actions'] = []
                data_project['actions'].append({'id': random_id(5), 'backend': 'github',
                                                'data': data_store, 'attrs': attrs_store})
                request.session['new_project'] = data_project

            elif datasources.gitlab.parse_input_data(repo_url, gitlab_instance.endpoint) != (None, None):
                if not request.user.is_authenticated or not request.user.gltokens.filter(
                        instance__slug='gitlab').exists():
                    error = True
                    continue

                commits = True
                issues = True
                forks = False
                data_owner, data_repo = datasources.gitlab.parse_input_data(repo_url, gitlab_instance.endpoint)
                if data_owner and data_repo:
                    data_store = f'{data_owner}/{data_repo}'
                    attrs_store = {'Commits': commits, 'Issues/MRs': issues}
                elif data_owner:
                    data_store = data_owner
                    attrs_store = {'Commits': commits, 'Issues/MRs': issues, 'Forks': forks}
                else:
                    error = True
                    continue

                data_project = request.session.get('new_project')
                if data_project is None:
                    data_project = {}
                if 'actions' not in data_project:
                    data_project['actions'] = []
                data_project['actions'].append({'id': random_id(5), 'backend': 'gitlab', 'instance': 'gitlab',
                                                'data': data_store, 'attrs': attrs_store})
                request.session['new_project'] = data_project

            else:
                repo_url = repo_url.strip()

                data_project = request.session.get('new_project')
                if data_project is None:
                    data_project = {}
                if 'actions' not in data_project:
                    data_project['actions'] = []
                data_project['actions'].append(
                    {'id': random_id(5), 'backend': 'git', 'data': repo_url, 'attrs': {'Commits': True}})
                request.session['new_project'] = data_project

        if error:
            return {'status': 'error', 'message': 'Some entries have errors.'}

    else:
        return {'error': 'No backend specified'}


def create_project_delete(request):
    id_action = request.POST.get('delete')
    if id_action is None:
        return {'status': 'error', 'message': 'You need to select at least one item to remove'}

    data = request.session.get('new_project')
    if not data:
        return
    actions = data.get('actions', [])
    if id_action == 'all':
        actions = []
    else:
        index = next((i for i, item in enumerate(actions) if item['id'] == id_action), None)
        if index is not None:
            actions.pop(index)
    data['actions'] = actions
    request.session['new_project'] = data


def _validate_data_project(request, data):
    if not data:
        return 'No data found'
    if 'name' not in data:
        return 'You need to define a name for the report.'
    if len(data['name']) < 1 or len(data['name']) > 32:
        return 'Project name should be between 1 and 32 chars.'
    if request.user.is_authenticated and Project.objects.filter(creator=request.user, name=data['name']).exists():
        return 'You have the same name in another report. Try with a different one.'


def create_empty_user():
    user = User.objects.create_user(username=generate_random_uuid(length=96),
                                    first_name="Anonymous")
    user.set_unusable_password()
    user.save()
    anonym_user = AnonymousUser(user=user)
    anonym_user.save()
    return user


def request_new_project(request):
    """Create a new project and redirect to project"""
    if request.method != 'POST':
        return custom_405(request, request.method)

    project_data = request.session.get('new_project')

    twitter_notification = request.POST.get('twitter-notification')

    error = _validate_data_project(request, project_data)
    if not project_data.get('actions', None):
        error = 'You need to add at least one data source.'
    if error:
        # TODO: format error
        return custom_404(request, error)

    if settings.LIMITED_ACCESS and not request.user.is_authenticated:
        return custom_403(request, "You are not allowed to create a new account in this server. "
                                   "Ask any of the administrators for permission.")

    if not request.user.is_authenticated:
        user = create_empty_user()
        login(request, user)
    public = False if settings.LIMITED_ACCESS else True
    project = Project.objects.create(name=project_data['name'], creator=request.user, public=public)
    project.create_es_role()

    for action in project_data['actions']:
        backend = action.get('backend', None)
        if backend == 'gitlab':
            instance = GLInstance.objects.get(slug=action.get('instance', 'gitlab'))
            output = datasources.gitlab.analyze_data(project=project,
                                                     data=action['data'],
                                                     commits=action['attrs'].get('Commits', False),
                                                     issues=action['attrs'].get('Issues/MRs', False),
                                                     forks=action['attrs'].get('Forks', False),
                                                     instance=instance)
            if output and output['status'] != 'ok':
                error = output['message']
                break
        elif backend == 'github':
            output = datasources.github.analyze_data(project=project,
                                                     data=action['data'],
                                                     commits=action['attrs'].get('Commits', False),
                                                     issues=action['attrs'].get('Issues/PRs', False),
                                                     forks=action['attrs'].get('Forks', False))
            if output and output['status'] != 'ok':
                error = output['message']
                break
        elif backend == 'git':
            datasources.git.analyze_git(project, action['data'])
            project.update_elastic_role()
        elif backend == 'meetup':
            output = datasources.meetup.analyze_data(project=project, data=action['data'])
            if output and output['status'] != 'ok':
                error = output['message']
                break
        elif backend == 'stackexchange':
            output = datasources.stackexchange.analyze_data(project=project,
                                                            site=action['params']['site'],
                                                            tags=action['params']['tags'])
            if output and output['status'] != 'ok':
                error = output['message']
                break

    if twitter_notification:
        try:
            ITwitterNotify.objects.create(user=request.user,
                                          project=project,
                                          report_url=request.build_absolute_uri(
                                              reverse('show_project', kwargs={'project_id': project.id})))
        except:
            error = "Error creating the Twitter notification."

    if error:
        project.delete()
        return custom_404(request, error)

    del request.session['new_project']

    return HttpResponseRedirect(reverse('show_project', kwargs={'project_id': project.id}))


def request_project_fork(request, project_id):
    try:
        project = Project.objects.get(pk=project_id)
    except Project.DoesNotExist:
        return custom_404(request, "The report requested was not found in this server")

    if not request.user.is_authenticated:
        return custom_403(request)

    try:
        new_project = project.fork(request.user)
    except Exception as e:
        return custom_500(request, f'There was an error creating a copy for the report: {e}')
    else:
        return HttpResponseRedirect(reverse('show_project', kwargs={'project_id': new_project.id}))


def check_missing_tokens(request, user, backends, last_page):
    if 'GH' in backends and not user.ghtokens.exists():
        request.session['last_page'] = last_page
        return JsonResponse({'status': 'error',
                             'message': generate_request_token_message('GitHub'),
                             'redirect': reverse('github_oauth')}, status=401)
    if 'GL' in backends and not request.user.gltokens.filter(instance='gitlab').exists():
        request.session['last_page'] = last_page
        return JsonResponse({'status': 'error',
                             'message': generate_request_token_message('GitLab'),
                             'redirect': reverse('gitlab_oauth', kwargs={'backend': 'gitlab'})}, status=401)
    if 'GN' in backends and not request.user.gltokens.filter(instance='gnome').exists():
        request.session['last_page'] = last_page
        return JsonResponse({'status': 'error',
                             'message': generate_request_token_message('GNOME'),
                             'redirect': reverse('gitlab_oauth', kwargs={'backend': 'gnome'})}, status=401)
    if 'KD' in backends and not request.user.gltokens.filter(instance='kde').exists():
        request.session['last_page'] = last_page
        return JsonResponse({'status': 'error',
                             'message': generate_request_token_message('KDE'),
                             'redirect': reverse('gitlab_oauth', kwargs={'backend': 'kde'})}, status=401)
    if 'MU' in backends and not request.user.meetuptokens.exists():
        request.session['last_page'] = last_page
        return JsonResponse({'status': 'error',
                             'message': generate_request_token_message('Meetup'),
                             'redirect': reverse('meetup_oauth')}, status=401)
    if 'SE' in backends and not request.user.stackexchangetokens.exists():
        request.session['last_page'] = last_page
        return JsonResponse({'status': 'error',
                             'message': generate_request_token_message('StackExchange'),
                             'redirect': reverse('stack_oauth')}, status=401)


def request_refresh_project(request, project_id):
    """Refresh all the project"""
    try:
        project = Project.objects.get(id=project_id)
    except Project.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': f"Report {project_id} does not exist"},
                            status=404)

    if not request.user.is_authenticated:
        return JsonResponse({'status': 'error', 'message': f"You are not authenticated."}, status=400)

    backends = project.repository_set.values_list('backend', flat=True).distinct()
    current_page = reverse('show_project', kwargs={'project_id': project_id})
    response = check_missing_tokens(request, request.user, backends, current_page)
    if response:
        return response

    refresh_count = 0
    for repo in project.repository_set.select_subclasses():
        if repo.refresh(request.user):
            refresh_count += 1

    return JsonResponse({'status': 'reanalyze',
                         'message': f"Refreshing {refresh_count} repositories"})


@require_http_methods(['POST'])
def request_project_autorefresh(request, project_id):
    """Enable auto refresh of repositories"""
    if request.method != 'POST':
        JsonResponse({'status': 'error', 'message': f"Method not allowed"},
                     status=403)

    try:
        project = Project.objects.get(id=project_id)
    except Project.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': f"Project {project_id} does not exist"},
                            status=404)

    if not request.user.is_authenticated or (request.user != project.creator and not request.user.is_superuser):
        return JsonResponse({'message': 'You are not allowed to modify this report'},
                            status=404)

    if not (settings.AUTOREFRESH_ENABLED or request.user.is_superuser):
        return JsonResponse({'message': 'Not authorized to perform this action. Ask an administrator'},
                            status=403)

    refresh = request.POST.get('refresh')
    if refresh == 'enabled':
        project.autorefresh = True
        project.save()
        scheduled_date = datetime.datetime.now() + datetime.timedelta(hours=1)
        ScheduledIntention.objects.get_or_create(intention_class='cauldron_apps.cauldron.models.IRefreshProject',
                                                 kwargs={'project_id': project.id, 'user_id': request.user.id},
                                                 user=request.user,
                                                 scheduled_at=scheduled_date)
        return JsonResponse({'status': 'ok', 'message': "Refresh report every 24 hours."})
    elif refresh == 'disabled':
        project.autorefresh = False
        project.save()
        ScheduledIntention.objects.filter(intention_class='cauldron_apps.cauldron.models.IRefreshProject') \
            .filter(kwargs__project_id=project.id).delete()
        return JsonResponse({'status': 'ok', 'message': "Stop refreshing report."})
    else:
        return JsonResponse({'status': 'error', 'message': f"refresh value not in ('enabled', 'disabled')"},
                            status=404)


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
    context['tab'] = request.GET.get('tab', 'overview')

    available_tags = ['overview', 'activity-git', 'activity-issues', 'activity-reviews', 'community-overview']
    if context['tab'] not in available_tags:
        context['tab'] = 'overview'

    if request.user.is_authenticated:
        context['user_projects'] = request.user.project_set.all()
        context['other_projects'] = Project.objects.exclude(creator=request.user)
    else:
        context['other_projects'] = Project.objects.all()

    if projects.filter(repository=None).count() > 0:
        context['message_error'] = "Some of the selected reports do not have repositories..."
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
            data = metrics.get_category_compare_metrics(projects, context['tab'], urls, from_date, to_date)
            context['metrics'] = data['metrics']
            context['charts'] = data['charts']

    return render(request, 'cauldronapp/compare/projects_compare.html', context=context)


def request_compare_projects_metrics(request):
    """Obtain the metrics related to a projects comparison for a category. By default overview"""
    if request.method != 'GET':
        return custom_405(request, request.method)

    category = request.GET.get('tab', 'overview')

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

    if projects.filter(repository=None).count() > 0:
        return custom_403(request, "Some of the selected reports do not have repositories...")

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

    compare_metrics = dict()
    if projects.count() > 0:
        compare_metrics = metrics.get_category_compare_metrics(projects, category, urls, from_date, to_date)

    return JsonResponse(compare_metrics)


def request_project_metrics(request, project_id):
    """Obtain the metrics related to a project for a category. By default overview"""
    if request.method != 'GET':
        return custom_405(request, request.method)

    category = request.GET.get('tab', 'overview')

    try:
        project = Project.objects.get(pk=project_id)
    except Project.DoesNotExist:
        return custom_404(request, "The report requested was not found in this server")

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


def get_available_dashboards(project):
    output = []
    token = utils.get_jwt_key('Dashboards', project.projectrole.backend_role)
    with requests.Session() as client:
        client.get(f"{KIB_IN_URL}/", params={'jwtToken': token})
        res = client.get(f"{KIB_IN_URL}/api/saved_objects/_find", params={'default_search_operator': 'AND',
                                                                          'page': 1,
                                                                          'per_page': 1000,
                                                                          'type': 'dashboard'})
        if res.ok:
            data = res.json()
            for dashboard in data['saved_objects']:
                output.append({
                    'name': dashboard['attributes']['title'],
                    'id': dashboard['id']
                })

    return output


def request_project_export(request, project_id):
    """View for data sources that can be exported for a report"""
    if settings.LIMITED_ACCESS and request.user and not request.user.is_authenticated:
        return custom_403(request, "You are not allowed to export data."
                                   "Ask any of the administrators for permission.")

    try:
        project, context = project_common(request, project_id)
    except Project.DoesNotExist:
        return custom_404(request, "The project requested was not found in this server")

    context['has_git'] = GitRepository.objects.filter(projects=project).exists()
    context['has_github'] = GitHubRepository.objects.filter(projects=project).exists()
    context['has_gitlab'] = GitLabRepository.objects.filter(projects=project).exists()
    context['has_meetup'] = MeetupRepository.objects.filter(projects=project).exists()
    context['has_stack'] = StackExchangeRepository.objects.filter(projects=project).exists()

    dashboards = get_available_dashboards(project)

    context['kbn_reports'] = project.kbn_report.order_by('-created')[:8]

    context['show_export'] = True

    context['available_dashboards'] = dashboards

    return render(request, 'cauldronapp/project/project.html', context=context)


def request_project_export_status(request, project_id):
    try:
        project = Project.objects.get(pk=project_id)
    except Project.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'report not found'}, status=404)
    summary = project.export_summary()
    return JsonResponse(summary)


def request_commits_by_month(request):
    if not request.user.is_authenticated or not request.user.is_superuser:
        return JsonResponse({'status': 'error', 'message': 'Not authorized'}, status=403)

    if request.method == 'POST':
        ICommitsByMonth.objects.get_or_create(defaults={'user': request.user})

    response = {
        'status': 'unknown'
    }
    result = ReportsCommitsByMonth.objects.first()
    if result:
        response['status'] = 'completed'
        response['location'] = '/download/' + result.location
        response['last-updated'] = result.created

    # Check if a new intention is running
    intention = ICommitsByMonth.objects.first()
    if intention:
        response['status'] = 'running'
        response['progress'] = intention.progress

    return JsonResponse(response)


def report_last_modified(request, project_id, *args, **kwargs):
    try:
        project = Project.objects.get(pk=project_id)
        repo = project.repository_set.latest('last_refresh')
        if repo:
            return repo.last_refresh
    except Project.DoesNotExist:
        return None


@last_modified(report_last_modified)
def request_project_stats_svg(request, project_id):
    try:
        project = Project.objects.get(pk=project_id)
    except Project.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'report not found'}, status=404)

    context = {
        'project': project,
        'metrics': metrics.report_svg_yoy_stats(project)
    }

    return render(request, 'cauldronapp/svg/report_stats.svg', context=context, content_type='image/svg+xml')


@last_modified(report_last_modified)
def request_project_git_contributors_svg(request, project_id):
    try:
        project = Project.objects.get(pk=project_id)
    except Project.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'report not found'}, status=404)

    epoch = datetime.datetime.fromtimestamp(0)
    now = datetime.datetime.now()
    elastic = metrics.get_elastic_project(project)

    context = {
        'git_contributors': metrics.community_commits.authors_active(elastic=elastic,
                                                                     urls=None,
                                                                     from_date=epoch,
                                                                     to_date=now)
    }

    return render(request, 'cauldronapp/svg/git_contributors.svg', context=context, content_type='image/svg+xml')


@last_modified(report_last_modified)
def request_project_export_svg(request, project_id, metric_name):
    try:
        project = Project.objects.get(pk=project_id)
    except Project.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'report not found'}, status=404)

    # key: name, function, length. Length from https://img.shields.io/badge/Issue%20authors-50-brightgreen + 5
    metrics_map = {
        'git_commits': ('Commits', metrics.activity_commits.git_commits, 52),
        'git_contributors': ('Contributors', metrics.community_commits.authors_active, 72),
        'git_lines_commits': ('Commits/Line', metrics.activity_commits.git_lines_commit, 81),
        'issues_created': ('Issues created', metrics.activity_issues.issues_opened, 86),
        'issues_closed': ('Issues closed', metrics.activity_issues.issues_closed, 78),
        'issues_authors': ('Issue authors', metrics.community_issues.active_submitters, 80),
        'issues_time_to_close': ('Issues Time to close', metrics.performance_issues.median_time_to_close, 118),
        'reviews_created': ('Reviews created', metrics.activity_reviews.reviews_opened, 96),
        'reviews_closed': ('Reviews closed', metrics.activity_reviews.reviews_closed, 88),
        'reviews_authors': ('Reviews authors', metrics.community_reviews.active_submitters, 96),
        'reviews_time_to_close': ('Reviews Time to close', metrics.performance_reviews.median_time_to_close, 128)
    }

    metric = metrics_map.get(metric_name)
    if not metric:
        return JsonResponse({'status': 'error', 'message': 'metric not found'}, status=404)

    epoch = datetime.datetime.fromtimestamp(0)
    now = datetime.datetime.now()
    elastic = metrics.get_elastic_project(project)

    text1 = metric[0]
    text2 = round(metric[1](elastic=elastic, urls=None, from_date=epoch, to_date=now), 2)

    text1w = metric[2]
    text2w = len(str(text2)) * 7
    box2x = 16 + text1w
    text2x = box2x + 4
    width = text2x + text2w + 4
    context = {
        'text1': text1,
        'text2': text2,
        'size': {
            'width': width,
            'box2x': box2x,
            'text2x': text2x,
            'box2w': width - text2x + 4
        }
    }

    return render(request, 'cauldronapp/svg/common_badge.svg', context=context, content_type='image/svg+xml')


def request_project_kibana_report(request, project_id):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Only POST methods allowed'}, status=405)
    if not request.user.is_authenticated:
        return JsonResponse({'status': 'error', 'message': 'only allowed for authenticated users'}, status=403)
    try:
        project = Project.objects.get(pk=project_id)
    except Project.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'report not found'}, status=404)

    dashboard_id = request.POST.get('dashboard', 'a834f080-41b1-11ea-a32a-715577273fe3')
    dashboard_format = request.POST.get('format', 'pdf')
    date_range = request.POST.get('date-range', '')
    if dashboard_id == 'all':
        dashboard_name = 'All dashboards'
    else:
        dashboards = get_available_dashboards(project)
        dashboard_name = dashboard_id
        for d in dashboards:
            if d['id'] == dashboard_id:
                dashboard_name = d['name']
                break
    try:
        fd, td = date_range.split('-')
        from_date = datetime.datetime.strptime(fd.strip(), '%Y/%m/%d')
        to_date = datetime.datetime.strptime(td.strip(), '%Y/%m/%d')
    except:
        from_date, to_date = None, None

    if not from_date:
        from_date = datetime.datetime.utcnow() - datetime.timedelta(days=365)
    if not to_date:
        to_date = datetime.datetime.utcnow()

    report = ProjectKibanaReport.objects.create(project=project,
                                                dashboard=dashboard_id,
                                                dashboard_name=dashboard_name,
                                                format=dashboard_format,
                                                from_date=from_date,
                                                to_date=to_date)
    IReportKbn.objects.create(user=request.user, kbn_report=report)

    return HttpResponseRedirect(reverse('project_export', kwargs={'project_id': project.id}))


def request_project_export_create(request, project_id):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Only POST methods allowed'}, status=405)
    try:
        project = Project.objects.get(id=project_id)
    except Project.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'report not found'}, status=404)
    backend = request.POST.get('backend', None)
    if not backend:
        return JsonResponse({'status': 'error', 'message': 'backend not defined'}, status=404)
    if not request.user.is_authenticated:
        return JsonResponse({'status': 'error', 'message': 'only allowed for authenticated users'}, status=403)
    if backend.upper() not in Backends.names:
        return JsonResponse({'status': 'error', 'message': f'invalid backend {backend}'}, status=404)
    bk = Backends[backend.upper()]

    IExportCSV.objects.get_or_create(defaults={'user': request.user}, project=project, backend=bk)

    return JsonResponse({'status': 'ok'})


def request_delete_project(request, project_id):
    if request.method != 'POST':
        return custom_405(request, request.method)

    try:
        project = Project.objects.get(id=project_id)
    except Project.DoesNotExist:
        return custom_404(request, "The report requested was not found in this server")

    owner = request.user.is_authenticated and request.user == project.creator
    if not owner and not request.user.is_superuser:
        return custom_403(request)

    delete_project(project)

    return JsonResponse({'status': 'Ok', 'id': project_id, 'message': 'Report deleted successfully'})


def delete_project(project):
    # Remove tasks in a transaction atomic
    with transaction.atomic():
        for repo in project.repository_set.select_subclasses():
            repo.remove_intentions(project.creator)
    odfe_api = OpendistroApi(ES_IN_URL, settings.ES_ADMIN_PASSWORD)
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
        return custom_404(request, "The report requested was not found in this server")

    is_owner = request.user.is_authenticated and request.user == project.creator
    if not is_owner and not request.user.is_superuser:
        return custom_403(request)

    if request.method != 'GET':
        return custom_405(request, request.method)

    if not hasattr(project.creator, 'userworkspace'):
        create_workspace(project.creator)

    name = project.creator.first_name.encode('utf-8', 'ignore').decode('ascii', 'ignore')
    jwt_key = utils.get_jwt_key(name, [project.projectrole.backend_role,
                                       project.creator.userworkspace.backend_role,
                                       'br_download_reports'])

    url = "{}/app/kibana?jwtToken={}&security_tenant={}#/dashboard/a9513820-41c0-11ea-a32a-715577273fe3".format(
        settings.KIB_OUT_URL,
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
    odfe_api = OpendistroApi(ES_IN_URL, settings.ES_ADMIN_PASSWORD)
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
    obj = kibana_objects.export_all_objects(KIB_IN_URL, settings.ES_ADMIN_PASSWORD, "global")
    kibana_objects.import_object(KIB_IN_URL, settings.ES_ADMIN_PASSWORD, obj, tenant_name)


def remove_workspace(user):
    """
    Remove the Tenant of a user and all the roles associated
    :param user:
    :return:
    """
    odfe_api = OpendistroApi(ES_IN_URL, settings.ES_ADMIN_PASSWORD)
    odfe_api.delete_mapping(user.userworkspace.tenant_role)
    odfe_api.delete_role(user.userworkspace.tenant_role)
    odfe_api.delete_tenant(user.userworkspace.tenant_name)
    user.userworkspace.delete()


def request_public_kibana(request, project_id):
    """Redirect to public Kibana"""
    if settings.LIMITED_ACCESS and not request.user.is_authenticated:
        return custom_403(request, "You are not allowed to open Kibana. "
                                   "Ask any of the administrators for permission.")

    project = Project.objects.filter(id=project_id).first()
    if not project:
        return custom_404(request, "The report requested was not found in this server")

    if request.method != 'GET':
        return custom_405(request, request.method)

    jwt_key = utils.get_jwt_key(f"Public {project_id}", [project.projectrole.backend_role, 'br_download_reports'])

    url = f"{settings.KIB_OUT_URL}/app/kibana" \
          f"?jwtToken={jwt_key}&security_tenant=global#/dashboard/a834f080-41b1-11ea-a32a-715577273fe3"

    return HttpResponseRedirect(url)


def request_kibana_admin(request):
    if not request.user.is_authenticated or not request.user.is_superuser:
        return custom_403(request)

    jwt_key = utils.get_jwt_key('admin', 'admin')

    url = "{}/app/discover?jwtToken={}".format(
        settings.KIB_OUT_URL,
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
        IGHRaw.objects.filter(user=request.user, job__isnull=True, repo__instance='GitHub').delete()
        IAddGHOwner.objects.filter(user=request.user, job__isnull=True, instance='GitHub').delete()
        request.user.ghtokens.filter(instance='GitHub').delete()
        return JsonResponse({'status': 'ok'})
    elif identity == 'meetup':
        IMeetupRaw.objects.filter(user=request.user, job__isnull=True).delete()
        request.user.meetuptokens.delete()
        return JsonResponse({'status': 'ok'})
    elif identity == 'stackexchange':
        IStackExchangeRaw.objects.filter(user=request.user, job__isnull=True).delete()
        request.user.stackexchangetokens.delete()
        return JsonResponse({'status': 'ok'})
    gl_instance = GLInstance.objects.filter(slug=identity).first()
    if gl_instance:
        IGLRaw.objects.filter(user=request.user, job__isnull=True, repo__instance=gl_instance).delete()
        IAddGLOwner.objects.filter(user=request.user, job__isnull=True, instance=gl_instance).delete()
        request.user.gltokens.filter(instance=gl_instance).delete()
        return JsonResponse({'status': 'ok'})

    return JsonResponse({'status': 'error', 'message': 'Unknown identity: {}'.format(identity)})


def request_unlink_account(request):
    """Function for removing a linked account from a user."""
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Only POST methods allowed'}, status=405)

    if not request.user.is_authenticated:
        return JsonResponse({'status': 'error', 'message': 'You are not logged in'}, status=401)

    identity = request.POST.get('identity', None)
    if identity == 'twitter':
        OauthUser.objects.filter(user=request.user, backend='twitter').delete()
        return JsonResponse({'status': 'ok'})

    return JsonResponse({'status': 'error', 'message': 'Unknown identity: {}'.format(identity)})


def create_context(request):
    """
    Create a new context dict with some common information among views
    :param request:
    :return:
    """
    context = dict()

    # Information for the photo and the profile
    context['authenticated'] = request.user.is_authenticated
    if request.user.is_authenticated:
        context['auth_user_username'] = request.user.first_name
        oauth_user = OauthUser.objects.filter(user=request.user, photo__isnull=False).first()
        if oauth_user:
            context['photo_user'] = oauth_user.photo
        else:
            context['photo_user'] = '/static/img/profile-default.png'

        # Banner message
        context['banner_messages'] = BannerMessage.objects.exclude(read_by=request.user)

    # Message that should be shown to the user
    context['alert_notification'] = request.session.pop('alert_notification', None)

    # Information about Hatstall
    if settings.HATSTALL_ENABLED:
        context['hatstall_url'] = "/hatstall"

    # Plausible Analytics
    context['plausible_analytics_enabled'] = settings.PLAUSIBLE_ANALYTICS_ENABLED
    context['plausible_analytics_url'] = settings.PLAUSIBLE_ANALYTICS_URL

    # Google Analytics
    if settings.GOOGLE_ANALYTICS_ID:
        context['google_analytics_id'] = settings.GOOGLE_ANALYTICS_ID

    # Other
    context['pricing_enabled'] = settings.PRICING_ENABLED

    # Data sources enabled (git excluded)
    context['data_sources_enabled'] = {
        'github': bool(settings.GH_CLIENT_ID),
        'gitlab': bool(settings.GL_CLIENT_ID_GITLAB),
        'meetup': bool(settings.MEETUP_CLIENT_ID),
        'kde': bool(settings.GL_CLIENT_ID_KDE),
        'gnome': bool(settings.GL_CLIENT_ID_GNOME),
        'stack_exchange': bool(settings.STACK_EXCHANGE_CLIENT_ID),
        'twitter': bool(settings.TWITTER_CLIENT_ID),
    }

    # Limited Access
    context['LIMITED_ACCESS'] = settings.LIMITED_ACCESS

    # Branding
    context['CLOUD_CUSTOM_BRAND'] = settings.CLOUD_CUSTOM_BRAND
    context['CLOUD_CUSTOM_SUB_BRAND'] = settings.CLOUD_CUSTOM_SUB_BRAND

    # SPDX
    context['spdx_enabled'] = settings.SPDX_ENABLED

    return context


def request_project_summary(request, project_id):
    """Return a JSON with the summary of the project"""
    try:
        project = Project.objects.get(pk=project_id)
    except Project.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'report not found'})
    summary = project.summary()
    return JsonResponse(summary)


def request_ongoing_owners(request, project_id):
    """Return a JSON with the ongoing owners requested"""
    response = {'owners': []}
    gh_owners = IAddGHOwner.objects.filter(project_id=project_id)
    gl_owners = IAddGLOwner.objects.filter(project_id=project_id)
    for gh_owner in gh_owners:
        response['owners'].append({'backend': 'github', 'owner': gh_owner.owner})
    for gl_owner in gl_owners:
        response['owners'].append({'backend': gl_owner.instance.name, 'owner': gl_owner.owner})
    return JsonResponse(response)


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
    username = ''.join([choice(chars) for _ in range(length)])

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
    context['repos_gitlab_count'] = GitLabRepository.objects.exclude(projects=None).filter(instance='GitLab').count()
    context['repos_gnome_count'] = GitLabRepository.objects.exclude(projects=None).filter(instance='Gnome').count()
    context['repos_kde_count'] = GitLabRepository.objects.exclude(projects=None).filter(instance='KDE').count()
    context['repos_meetup_count'] = MeetupRepository.objects.exclude(projects=None).count()
    context['repos_stack_count'] = StackExchangeRepository.objects.exclude(projects=None).count()
    return context


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

        SORT_CHOICES = {
            'name': 'first_name',
            'joined': 'date_joined',
            'reports': 'project__count',
            'authorized': 'is_active',
            'admin': 'is_superuser',
        }

        COUNT_CHOICES = {
            'reports': 'project',
        }

        if sort_by in SORT_CHOICES:
            if sort_by in COUNT_CHOICES:
                users = users.annotate(Count(COUNT_CHOICES[sort_by]))

            users = users.order_by(SORT_CHOICES[sort_by])

            if reverse:
                users = users.reverse()

    p = Pages(users, 10)
    page_number = request.GET.get('page', 1)
    page_obj = p.pages.get_page(page_number)
    context['page_obj'] = page_obj
    context['pages_to_show'] = p.pages_to_show(page_obj.number)

    context['users'] = []
    for user in page_obj.object_list:
        user_entry = dict()
        user_entry['user'] = user
        user_entry['linked_accounts'] = {
            'github': OauthUser.objects.filter(user=user, backend='github').first(),
            'gitlab': OauthUser.objects.filter(user=user, backend='gitlab').first(),
            'gnome': OauthUser.objects.filter(user=user, backend='gnome').first(),
            'kde': OauthUser.objects.filter(user=user, backend='kde').first(),
            'meetup': OauthUser.objects.filter(user=user, backend='meetup').first(),
            'stackexchange': OauthUser.objects.filter(user=user, backend='stackexchange').first(),
            'twitter': OauthUser.objects.filter(user=user, backend='twitter').first(),
        }
        user_entry['tokens'] = {
            'github': GHToken.objects.filter(user=user, instance='GitHub').first(),
            'gitlab': {},
            'meetup': MeetupToken.objects.filter(user=user).first(),
            'stackexchange': StackExchangeToken.objects.filter(user=user).first(),
        }
        for instance in GLInstance.objects.values_list('slug', flat=True):
            user_entry['tokens']['gitlab'][instance] = GLToken.objects.filter(user=user,
                                                                              instance__slug=instance).first()
        context['users'].append(user_entry)

    return render(request, 'cauldronapp/admin/admin-users.html', context=context)


@require_http_methods(['POST'])
def request_add_user(request):
    """ Add a new user"""
    if not request.user.is_authenticated or not request.user.is_superuser:
        return JsonResponse({'status': 'error', 'message': 'You cannot create a new user'}, status=403)

    backend = request.POST.get('backend', None)
    username = request.POST.get('username', '').strip()
    is_admin = request.POST.get('admin', None)

    if backend not in ['github', 'gitlab', 'meetup', 'gnome', 'kde', 'stackexchange']:
        return JsonResponse({'status': 'error', 'message': f'Backend {backend} not found'}, status=400)

    if username == '':
        return JsonResponse({'status': 'error', 'message': 'username invalid'}, status=400)

    if OauthUser.objects.filter(username=username, backend=backend).exists():
        return JsonResponse(
            {'status': 'error', 'message': f'user {username} already exists for backend called {backend}'}, status=400)

    if settings.LIMITED_ACCESS:
        AuthorizedBackendUser.objects.get_or_create(backend=backend, username=username)

    user = create_django_user(username)

    # Create the backend entity and associate with the account
    OauthUser.objects.create(user=user,
                             backend=backend,
                             username=username)

    # If it is an admin user, upgrade it
    if is_admin:
        upgrade_to_admin(user)

    return JsonResponse({'status': 'ok'})


def authorize_user(request):
    """
    Authorize user to use Cauldron
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

    # Authorize user to use Cauldron
    user.is_active = True
    user.save()

    return HttpResponseRedirect(reverse('admin_page_users'))


def unauthorize_user(request):
    """
    Unauthorize user to use Cauldron
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
    user.is_active = False
    user.save()

    return HttpResponseRedirect(reverse('admin_page_users'))


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


def pricing(request):
    """
    View to show the Pricing of Cauldron
    :param request:
    :return:
    """
    context = create_context(request)

    if not settings.PRICING_ENABLED:
        return custom_404(request, "The URL requested was not found in this server")

    return render(request, 'cauldronapp/pricing.html', context=context)


def custom_403(request, message=None):
    """
    View to show the default 403 template
    :param message:
    :param request:
    :return:
    """
    context = create_context(request)
    context['title'] = "403 Forbidden"
    if message:
        context['description'] = message
    else:
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
