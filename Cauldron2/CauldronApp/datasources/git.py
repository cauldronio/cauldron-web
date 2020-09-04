from CauldronApp.models import GitRepository
from poolsched import api as sched_api


def analyze_git(project, url):
    """IMPORTANT: update the repo role after this call"""
    repo, created = GitRepository.objects.get_or_create(url=url)
    if created:
        repo.link_sched_repo()
    repo.projects.add(project)
    sched_api.analyze_git_repo_obj(project.creator, repo.repo_sched)
