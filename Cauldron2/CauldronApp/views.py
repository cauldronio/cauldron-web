from django.shortcuts import render
from django.http import HttpResponseRedirect, JsonResponse
from django.contrib.auth import login, logout
from django.contrib.auth.models import User

import os
import logging
import requests
import jwt
from urllib.parse import urlparse, urlencode
from random import choice
from string import ascii_lowercase, digits
from github import Github
from gitlab import Gitlab
from slugify import slugify
from archimedes.archimedes import Archimedes

from Cauldron2.settings import GH_CLIENT_ID, GH_CLIENT_SECRET, GL_CLIENT_ID, GL_CLIENT_SECRET, GL_PRIVATE_TOKEN, ES_URL, KIB_URL, ES_ADMIN_PSW
from CauldronApp.models import GithubUser, GitlabUser, Dashboard, Repository, Task, CompletedTask, AnonymousUser, ESUser
from CauldronApp.githubsync import GitHubSync


GH_ACCESS_OAUTH = 'https://github.com/login/oauth/access_token'
GH_URI_IDENTITY = 'https://github.com/login/oauth/authorize'

GL_ACCESS_OAUTH = 'https://gitlab.com/oauth/token'
GL_URI_IDENTITY = 'https://gitlab.com/oauth/authorize'
GL_REDIRECT_PATH = '/gitlab-login'


def homepage(request):
    context = create_context(request)

    dashboards = Dashboard.objects.filter()
    context_dbs = []
    for db in dashboards:
        status = get_dashboard_status(db.name)

        completed = sum(1 for repo in status['repos'] if repo['status'] == 'COMPLETED')
        context_dbs.append({'status': status['general'],
                            'name': db.name,
                            'id': db.id,
                            'completed': completed,
                            'total': len(status['repos'])})
    if request.user.is_authenticated:
        your_dashboards = Dashboard.objects.filter(creator=request.user)
        context_your_dbs = []
        for db in your_dashboards:
            status = get_dashboard_status(db.name)

            completed = sum(1 for repo in status['repos'] if repo['status'] == 'COMPLETED')
            context_your_dbs.append({'status': status['general'],
                                     'id': db.id,
                                     'name': db.name,
                                     'completed': completed,
                                     'total': len(status['repos'])})
    else:
        context_your_dbs = []

    # TODO: Generate a state for that session and store it in request.session. More security in Oauth
    context['dashboards'] = context_dbs
    context['your_dashboards'] = context_your_dbs
    context['gh_uri_identity'] = GH_URI_IDENTITY
    context['gh_client_id'] = GH_CLIENT_ID
    context['gl_uri_identity'] = GL_URI_IDENTITY
    context['gl_client_id'] = GL_CLIENT_ID
    context['gl_uri_redirect'] = request.build_absolute_uri(GL_REDIRECT_PATH)
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

    tricky_authentication(request, GithubUser, username, token, photo_url)

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
                              'redirect_uri': request.build_absolute_uri(GL_REDIRECT_PATH)},
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

    # TODO: Token modify to auth token. Modify all the TODOs with the same name
    token = GL_PRIVATE_TOKEN

    # Authenticate/register an user, and login
    gl = Gitlab(url='https://gitlab.com', private_token=token)
    gl.auth()
    username = gl.user.attributes['username']
    photo_url = gl.user.attributes['avatar_url']

    tricky_authentication(request, GitlabUser, username, token, photo_url)

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


# TODO: Add state
def request_edit_dashboard(request, dash_id):
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
    owner = request.POST.get('owner', None)
    url = request.POST.get('url', None)
    backend = request.POST.get('backend', None)

    if not action or action not in ('add', 'delete'):
        return JsonResponse({'status': 'error', 'message': 'Action not found in the POST or action not allowed'},
                            status=400)

    if not backend or backend not in ('github', 'gitlab', 'git'):
        return JsonResponse({'status': 'error', 'message': 'Backend not found in the POST or action not allowed'},
                            status=400)

    if not url and not owner:
        return JsonResponse({'status': 'error', 'message': 'We need a url or a owner to add/delete'},
                            status=400)

    if action == 'delete':
        print('deleting repository [{}|{}] from dashboard[{}]'.format(backend, url, dash_id))
        if not url or not backend:
            return JsonResponse({'status': 'error', 'message': 'We need a url and a backend for deleting'},
                                status=400)
        repo = Repository.objects.filter(url=url, backend=backend).first()
        if not repo:
            return JsonResponse({'status': 'error', 'message': 'Repository not found'},
                                status=404)
        repo.dashboards.remove(dash)
        task = Task.objects.filter(repository=repo).first()
        if task and task.user == dash.creator and not task.worker_id:
            task.delete()

        return JsonResponse({'status': 'deleted'})

    if backend == 'github':
        if not hasattr(request.user, 'githubuser'):
            params = urlencode({'client_id': GH_CLIENT_ID})
            gh_url_oauth = "{}?{}".format(GH_URI_IDENTITY, params)
            return JsonResponse({'status': 'error',
                                 'message': 'We need your GitHub token for analyzing this kind of repositories',
                                 'redirect': gh_url_oauth},
                                status=401)

        if owner:
            gh_sync = GitHubSync(request.user.githubuser.token)
            try:
                git_list, github_list = gh_sync.get_repo(owner, False)
            except Exception:
                logging.warning("Error for GitHub owner {}".format(owner))
                return JsonResponse({'status': 'error', 'message': 'Error from GitHub API. Does that user exist?'},
                                    status=500)
            for url in github_list:
                repo = add_to_dashboard(dash, backend, url)
                start_task(repo, request.user, False)

            for url in git_list:
                repo = add_to_dashboard(dash, 'git', url)
                start_task(repo, request.user, False)
        elif url:
            if not valid_github_url(url):
                return JsonResponse({'status': 'error', 'message': 'Invalid GitHub URL format.'},
                                    status=400)
            # Add to github and git
            repo = add_to_dashboard(dash, backend, url)
            start_task(repo, request.user, False)
            repo = add_to_dashboard(dash, 'git', url + '.git')
            start_task(repo, request.user, False)

        return JsonResponse({'status': 'ok'})

    elif backend == 'gitlab':
        if not hasattr(request.user, 'gitlabuser'):
            params = urlencode({'client_id': GL_CLIENT_ID,
                                'response_type': 'code',
                                'redirect_uri': request.build_absolute_uri(GL_REDIRECT_PATH)})
            gh_url_oauth = "{}?{}".format(GL_URI_IDENTITY, params)
            return JsonResponse({'status': 'error',
                                 'message': 'We need your GitLab token for analyzing this kind of repositories',
                                 'redirect': gh_url_oauth},
                                status=401)

        if owner:
            try:
                gitlab_list, git_list = get_gl_repos(owner, request.user.gitlabuser.token)
            except Exception as e:
                logging.warning("Error for Gitlab owner {}: {}".format(owner, e.error_message))
                return JsonResponse({'status': 'error', 'message': 'Error from GitLab API. Does that user exist?'},
                                    status=500)

            for url in gitlab_list:
                repo = add_to_dashboard(dash, backend, url)
                start_task(repo, request.user, False)

            for url in git_list:
                repo = add_to_dashboard(dash, 'git', url)
                start_task(repo, request.user, False)
        elif url:
            if not valid_gitlab_url(url):
                return JsonResponse({'status': 'error', 'message': 'Invalid Gitlab URL format.'},
                                    status=400)
            # Add to gitlab and git
            repo = add_to_dashboard(dash, backend, url)
            start_task(repo, request.user, False)
            repo = add_to_dashboard(dash, 'git', url + '.git')
            start_task(repo, request.user, False)

        return JsonResponse({'status': 'ok'})

    elif backend == 'git':
        if not url:
            return JsonResponse({'status': 'error', 'message': 'No URL found for git repository.'},
                                status=400)
        repo = add_to_dashboard(dash, backend, url)
        start_task(repo, request.user, False)

        return JsonResponse({'status': 'ok'})

    else:
        return JsonResponse({'status': 'error', 'message': 'Backend not found'},
                            status=400)


def start_task(repo, user, restart=False):
    """
    Start a new task for the given repository
    :param repo: Repository object to analyze
    :param user: User that make the analysis
    :param restart: If the task is not pending or running, start it. Else only start if not completed before
    :return:
    """
    if not Task.objects.filter(repository=repo).first():
        if restart or not CompletedTask.objects.filter(repository=repo).first():
            new_task = Task(repository=repo, user=user)
            new_task.save()


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
    dash.name = "dashboard_{}".format(dash.id)
    dash.save()

    # Create the Kibana user associated to that dashboard
    kib_username = "dashboard_{}".format(dash.id)
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
    r = requests.put("{}/_opendistro/_security/api/internalusers/{}".format(ES_URL, name),
                     auth=('admin', ES_ADMIN_PSW),
                     json={"password": psw},
                     verify=False,
                     headers=headers)
    logging.info("{} - {}".format(r.status_code, r.text))
    r.raise_for_status()

    role_name = "role_{}".format(name)
    logging.info('Creating ES role for user: <{}>'.format(name))
    r = requests.put("{}/_opendistro/_security/api/roles/{}".format(ES_URL, role_name),
                     auth=('admin', ES_ADMIN_PSW),
                     json={"indices": {'none':  {"*": ["READ"]}}},
                     verify=False,
                     headers=headers)
    logging.info("{} - {}".format(r.status_code, r.text))
    r.raise_for_status()

    logging.info('Creating ES role mapping for user: <{}>'.format(name))
    r = requests.put("{}/_opendistro/_security/api/rolesmapping/{}".format(ES_URL, role_name),
                     auth=('admin', ES_ADMIN_PSW),
                     json={"users": [name]},
                     verify=False,
                     headers=headers)
    logging.info("{} - {}".format(r.status_code, r.text))
    r.raise_for_status()

    logging.info('Import Index patterns')
    kib_url_parsed = urlparse(KIB_URL)
    kib_url_auth = "{}://{}:{}@{}".format(kib_url_parsed.scheme, name, psw, kib_url_parsed.netloc)
    archimedes = Archimedes(kib_url_auth, "CauldronApp/archimedes_panels/")
    archimedes.import_from_disk(obj_type='index-pattern', obj_id='gitlab_enriched', force=False)
    archimedes.import_from_disk(obj_type='index-pattern', obj_id='git_aoc_enriched', force=False)
    archimedes.import_from_disk(obj_type='index-pattern', obj_id='github_enrich', force=False)
    archimedes.import_from_disk(obj_type='index-pattern', obj_id='git_enrich', force=False)

    # Set default Index pattern
    logging.info('Set default index pattern')
    headers = {'Content-Type': 'application/json', 'kbn-xsrf': 'true'}
    requests.post('{}/api/kibana/settings/defaultIndex'.format(KIB_URL),
                  auth=(name, psw),
                  json={"value": "git_enrich"},
                  verify=False,
                  headers=headers)

    r.raise_for_status()

    es_user = ESUser(name=name, password=psw, role=role_name, dashboard=dashboard)
    es_user.save()


def request_import_panels(request, dash_id):
    dash = Dashboard.objects.filter(id=dash_id).first()
    if not dash:
        return JsonResponse({'status': 'error', 'message': 'Dashboard not found'}, status=404)

    if not request.user.is_authenticated:
        return JsonResponse({'status': 'error', 'message': 'You are not authenticated'}, status=401)

    if request.user != dash.creator:
        return JsonResponse({'status': 'error', 'message': 'This is not your dashboard'}, status=403)

    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Only POST method allowed'}, status=405)

    kib_url_parsed = urlparse(KIB_URL)
    kib_url_auth = "{}://{}:{}@{}".format(kib_url_parsed.scheme,
                                             dash.esuser.name,
                                             dash.esuser.password,
                                             kib_url_parsed.netloc)
    archimedes = Archimedes(kib_url_auth, "CauldronApp/archimedes_panels/")
    archimedes.import_from_disk(obj_type='dashboard', obj_id='Overview',
                                find=True, force=False)

    return JsonResponse({'status': 'ok'})


def add_to_dashboard(dash, backend, url):
    """
    Add a repository to a dashboard
    :param dash: Dashboard row from db
    :param url: url for the analysis
    :param backend: Identity used like github or gitlab. See models.py for more details
    :param task_creator: user to start a task with that repository
    :return: Repostory created
    """
    repo_obj = Repository.objects.filter(url=url, backend=backend).first()
    index_name = create_index_name(backend, url)
    if not repo_obj:
        repo_obj = Repository(url=url, backend=backend, index_name=index_name)
        repo_obj.save()
    # Add the repo to the dashboard
    repo_obj.dashboards.add(dash)
    return repo_obj


def create_index_name(backend, url):
    if backend in ('github', 'gitlab'):
        owner, repo = parse_url(url)
        return "{}_{}_{}".format(backend, owner, repo)
    else:
        # Like git
        try:
            owner, repo = parse_url(url[:-4])
            txt = slugify("{}_{}_{}".format('git', owner, repo), max_length=100)
        except Exception:
            # Its ok, let's call sluglify for that work
            txt = slugify("{}_{}".format('git', url), max_length=100)

        return txt


def get_dashboard_status(dash_name):
    """
    General status:
    If no repos -> UNKNOWN
    1. If any repo is running -> return RUNNING
    2. Else if any repo pending -> return PENDING
    3. Else if any repo error -> return ERROR
    4. Else -> return COMPLETED
    :param dash_name: name of the dashboard
    :return: Status of the dashboard depending on the the previous rules
    """
    repos = Repository.objects.filter(dashboards__name=dash_name)
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
        if task:
            item['created'] = task.created
            item['started'] = task.started
            item['completed'] = None
            info['repos'].append(item)
            continue

        compl_task = CompletedTask.objects.filter(repository=repo).order_by('-completed').first()
        if compl_task:
            item['created'] = compl_task.created
            item['started'] = compl_task.started
            item['completed'] = compl_task.completed
            info['repos'].append(item)
            continue

        # If we are here something wrong is happening. We leave everything as None
        # just in case there is a race condition while creating the task
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
        context['dashboard_status'] = get_dashboard_status(dash.name)['general']
        context['repositories'] = Repository.objects.filter(dashboards__id=dash_id)

    context['editable'] = request.user.is_authenticated and request.user == dash.creator

    # Repositories
    gh_repos = Repository.objects.filter(backend='github', dashboards__id=dash_id)
    gl_repos = Repository.objects.filter(backend='gitlab', dashboards__id=dash_id)
    git_repos = Repository.objects.filter(backend='git', dashboards__id=dash_id)
    context['gh_repositories'] = list(repo for repo in gh_repos)
    context['gl_repositories'] = list(repo for repo in gl_repos)
    context['git_repositories'] = list(repo for repo in git_repos)
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

    # TODO: The user should be stored in db
    user = "dashboard_{}".format(dash_id)
    roles = ""
    jwt_key = jwt_sign_user(user, roles)

    update_indices(dash_id)

    return HttpResponseRedirect(KIB_URL + "/?jwtToken=" + jwt_key)


def jwt_sign_user(user, roles):
    with open('jwtR256.key', 'r') as f_private:
        private_key = f_private.read()

    claims = {
        "user": user,
        "roles": roles
    }

    return jwt.encode(claims, private_key, algorithm='RS256').decode('utf-8')


def update_indices(dash_id):
    repos = Repository.objects.filter(dashboards__id=dash_id)
    role_name = "role_dashboard_{}".format(dash_id)
    if not len(repos):
        return
    role = {
        "indices": {
            # Here comes each index
        }
    }
    for repo in repos:
        role['indices']["*{}".format(repo.index_name)] = {"*": ["READ"]}

    headers = {'Content-Type': 'application/json'}
    r = requests.put("{}/_opendistro/_security/api/roles/{}".format(ES_URL, role_name),
                     auth=('admin', ES_ADMIN_PSW),
                     json=role,
                     verify=False,
                     headers=headers)
    r.raise_for_status()


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
    context['gl_uri_redirect'] = request.build_absolute_uri(GL_REDIRECT_PATH)

    # Information for the photo and the profile
    context['authenticated'] = request.user.is_authenticated
    if hasattr(request.user, 'githubuser'):
        context['auth_user_username'] = request.user.githubuser.username
        context['photo_user'] = request.user.githubuser.photo
    elif hasattr(request.user, 'gitlabuser'):
        context['auth_user_username'] = request.user.gitlabuser.username
        context['photo_user'] = request.user.gitlabuser.photo
    else:
        context['auth_user_username'] = 'Unknown'
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


def dash_status(request, dash_name):
    status = get_dashboard_status(dash_name)
    return JsonResponse({'status': status})


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
    gl = Gitlab(url='https://gitlab.com', private_token=token)
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
