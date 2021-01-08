from CauldronApp.models import GitRepository
from cauldron_apps.poolsched_git.api import analyze_git_repo_obj
from cauldron_apps.cauldron_actions.models import AddGitRepoAction


def analyze_git(project, url):
    """IMPORTANT: update the repo role after this call"""
    repo, created = GitRepository.objects.get_or_create(url=url)
    if created:
        repo.link_sched_repo()
    repo.projects.add(project)
    analyze_git_repo_obj(project.creator, repo.repo_sched)
    AddGitRepoAction.objects.create(creator=project.creator, project=project, repository=repo)
