import re

from CauldronApp.models import GitLabRepository
from CauldronApp.datasources import git
from cauldron_apps.poolsched_gitlab.api import analyze_gl_repo_obj
from cauldron_apps.cauldron.models import IAddGLOwner
from cauldron_apps.poolsched_gitlab.models import GLInstance
from cauldron_apps.cauldron_actions.models import AddGitLabOwnerAction, AddGitLabRepoAction


def parse_input_data(data, domain):
    """Return a tuple (owner, repository). Return None in owner or repository in the case was not found"""
    domain_escaped = re.escape(domain)
    gl_user_regex = '([a-zA-Z0-9_\.][a-zA-Z0-9_\-\.]{1,200}[a-zA-Z0-9_\-]|[a-zA-Z0-9_])'
    gl_repo_regex = '((?:[a-zA-Z0-9_\.][a-zA-Z0-9_\-\.]*(?:\/)?)+)'
    data = data.strip()

    re_user = re.match('^{}$'.format(gl_user_regex), data)
    if re_user:
        return re_user.groups()[0], None
    re_url_user = re.match(f'^{domain_escaped}\/{gl_user_regex}\/?$', data)
    if re_url_user:
        return re_url_user.groups()[0], None
    re_url_repo = re.match(f'^{domain_escaped}\/{gl_user_regex}\/{gl_repo_regex}(?:.git)?$', data)
    if re_url_repo:
        return re_url_repo.groups()[0], re_url_repo.groups()[1]
    re_user_repo = re.match(f'{gl_user_regex}/{gl_repo_regex}$', data)
    if re_user_repo:
        return re_user_repo.groups()[0], re_user_repo.groups()[1]

    return None, None


def analyze_gitlab(project, owner, repo, instance):
    """IMPORTANT: update the repo role after this call"""
    repo, created = GitLabRepository.objects.get_or_create(owner=owner, repo=repo, instance=instance)
    if created:
        repo.link_sched_repo()
    repo.projects.add(project)
    analyze_gl_repo_obj(project.creator, repo.repo_sched)
    AddGitLabRepoAction.objects.create(creator=project.creator, project=project, repository=repo)


def analyze_data(project, data, commits=False, issues=False, forks=False, instance='GitLab'):
    instance_obj = GLInstance.objects.get(name=instance)
    owner, repository = parse_input_data(data, instance_obj.endpoint)

    if owner and not repository:
        token = project.creator.gltokens.filter(instance=instance_obj).first()
        if not token:
            return {'status': 'error',
                    'message': 'Token not found for the creator of the project',
                    'code': 400}
        IAddGLOwner.objects.create(user=project.creator,
                                   owner=owner,
                                   instance=instance_obj,
                                   project=project,
                                   commits=commits,
                                   issues=issues,
                                   forks=forks,
                                   analyze=True)
        AddGitLabOwnerAction.objects.create(creator=project.creator, project=project,
                                            instance=instance, owner=owner, commits=commits,
                                            issues=issues, forks=forks)
    elif owner and repository:
        if issues:
            token = project.creator.gltokens.filter(instance=instance_obj).first()
            if not token:
                return {'status': 'error',
                        'message': 'Token not found for the creator of the project',
                        'code': 400}
            repo_encoded = '%2F'.join(repository.strip('/').split('/'))
            analyze_gitlab(project, owner, repo_encoded, instance_obj)
        if commits:
            url = f"{instance_obj.endpoint}/{owner}/{repository}.git"
            git.analyze_git(project, url)
        project.update_elastic_role()
    else:
        return {'status': 'error',
                'message': "We couldn't guess what do you mean with that string. "
                           "Valid: URL user, URL repo, user, user/repo or user/group/.../repo",
                'code': 400}

    return {'status': 'ok', 'code': 200}
