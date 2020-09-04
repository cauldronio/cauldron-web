import re
from github import Github

from CauldronApp.models import GitHubRepository
from CauldronApp.datasources import git
from poolsched import api as sched_api


def parse_input_data(data):
    """Return a tuple (owner, repository). Return None in owner or repository in the case was not found"""
    owner_regex = '([a-zA-Z0-9](?:[a-zA-Z0-9]|-[a-zA-Z0-9]){1,38})'
    repo_regex = '([a-zA-Z0-9\.\-\_]{1,100})'
    data = data.strip()

    re_owner = re.match(f'^{owner_regex}$', data)
    if re_owner:
        return re_owner.groups()[0], None
    re_url_owner = re.match(f'^https?://github\.com/{owner_regex}/?$', data)
    if re_url_owner:
        return re_url_owner.groups()[0], None
    re_url_repo = re.match(f'^https?://github\.com/{owner_regex}/{repo_regex}(?:.git)?$', data)
    if re_url_repo:
        return re_url_repo.groups()[0], re_url_repo.groups()[1]
    re_owner_repo = re.match(f'^{owner_regex}/{repo_regex}$', data)
    if re_owner_repo:
        return re_owner_repo.groups()[0], re_owner_repo.groups()[1]

    return None, None


def analyze_github(project, owner, repo):
    """IMPORTANT: update the repo role after this call"""
    repo, created = GitHubRepository.objects.get_or_create(owner=owner, repo=repo)
    if not repo.repo_sched:
        repo.link_sched_repo()
    repo.projects.add(project)
    sched_api.analyze_gh_repo_obj(project.creator, repo.repo_sched)


def analyze_data(project, data, commits=False, issues=False, forks=False):
    """IMPORTANT: update the repo role after this call"""
    owner, repository = parse_input_data(data)

    if owner and not repository:
        token = project.creator.ghtokens.first()
        if not token:
            return {'status': 'error',
                    'message': 'Token not found for the creator of the project',
                    'code': 400}
        github = Github(token.token)

        repositories = github.get_user(owner).get_repos()
        for repo_gh in repositories:
            if not repo_gh.fork or forks:
                if issues:
                    analyze_github(project, owner, repo_gh.name)
                if commits:
                    git.analyze_git(project, repo_gh.clone_url)

    elif owner and repository:
        if issues:
            token = project.creator.ghtokens.first()
            if not token:
                return {'status': 'error',
                        'message': 'Token not found for the creator of the project',
                        'code': 400}
            analyze_github(project, owner, repository)
        if commits:
            url = f"https://github.com/{owner}/{repository}.git"
            git.analyze_git(project, url)
    else:
        return {'status': 'error',
                'message': "We couldn't guess what do you mean with that string. "
                           "Valid: URL user, URL repo, user or user/repo",
                'code': 400}

    return {'status': 'ok', 'code': 200}



