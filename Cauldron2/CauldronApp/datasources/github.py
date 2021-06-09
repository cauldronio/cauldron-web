import re

from cauldron_apps.poolsched_github.api import analyze_gh_repo_obj
from CauldronApp.datasources import git
from cauldron_apps.cauldron.models import IAddGHOwner, GitHubRepository, RepositoryMetrics
from cauldron_apps.cauldron_actions.models import AddGitHubRepoAction, AddGitHubOwnerAction


def parse_input_data(data):
    """Return a tuple (owner, repository). Return None in owner or repository in the case was not found"""
    owner_regex = '([a-zA-Z0-9](?:[a-zA-Z0-9]|-[a-zA-Z0-9]){1,38})'
    repo_regex = '([a-zA-Z0-9\.\-\_]{1,100})'
    data = data.strip()

    re_owner = re.match(f'^{owner_regex}$', data)
    if re_owner:
        return re_owner.groups()[0], None

    re_url_owner = re.match(f'^(?:https?:\/\/)?github\.com\/{owner_regex}\/?$', data)
    if re_url_owner:
        return re_url_owner.groups()[0], None

    re_url_repo = re.match(f'^(?:https?:\/\/)?github\.com\/{owner_regex}\/{repo_regex}(?:.git)?$', data)
    if re_url_repo:
        return re_url_repo.groups()[0], re_url_repo.groups()[1]

    re_owner_repo = re.match(f'^{owner_regex}\/{repo_regex}$', data)
    if re_owner_repo:
        return re_owner_repo.groups()[0], re_owner_repo.groups()[1]

    return None, None


def analyze_github(project, owner, repo, result):
    """IMPORTANT: update the repo role after this call"""
    repo, created = GitHubRepository.objects.get_or_create(owner=owner, repo=repo, defaults={'results': result})
    if not repo.repo_sched:
        repo.link_sched_repo()
    repo.projects.add(project)
    analyze_gh_repo_obj(project.creator, repo.repo_sched)
    AddGitHubRepoAction.objects.create(creator=project.creator, project=project, repository=repo)


def analyze_data(project, data, commits=False, issues=False, forks=False):
    owner, repository = parse_input_data(data)

    if owner and not repository:
        token = project.creator.ghtokens.first()
        if not token:
            return {'status': 'error',
                    'message': 'Token not found for the creator of the project',
                    'code': 400}
        IAddGHOwner.objects.create(user=project.creator,
                                   owner=owner,
                                   project=project,
                                   commits=commits,
                                   issues=issues,
                                   forks=forks,
                                   analyze=True)
        AddGitHubOwnerAction.objects.create(creator=project.creator, project=project,
                                            owner=owner, commits=commits, issues=issues, forks=forks)
    elif owner and repository:
        result, _ = RepositoryMetrics.objects.get_or_create(name=f'GitHub {owner}/{repository}')
        if issues:
            token = project.creator.ghtokens.first()
            if not token:
                return {'status': 'error',
                        'message': 'Token not found for the creator of the project',
                        'code': 400}
            analyze_github(project, owner, repository, result)
        if commits:
            url = f"https://github.com/{owner}/{repository}.git"
            git.analyze_git(project, url, result)
        project.update_elastic_role()
    else:
        return {'status': 'error',
                'message': "We couldn't guess what do you mean with that string. "
                           "Valid: URL user, URL repo, user or user/repo",
                'code': 400}

    return {'status': 'ok', 'code': 200}
