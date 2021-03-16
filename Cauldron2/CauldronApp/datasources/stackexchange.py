import re

from cauldron_apps.cauldron_actions.models import AddStackExchangeRepoAction
from cauldron_apps.cauldron.models import StackExchangeRepository
from cauldron_apps.poolsched_stackexchange.api import analyze_stack_repo_obj


def parse_tags(tagged):
    """Return the tags in the format expected by StackExchange API
    tagged can be split by spaces, commas, slash, or semicolon
    """
    out = re.sub('\s*;\s*', repl=';', string=tagged.strip())
    out = re.sub('\s*,\s*', repl=';', string=out)
    out = re.sub('\s*\/\s*', repl=';', string=out)
    out = re.sub('\s+', repl=';', string=out)
    return out


def analyze_stackexchange(project, site, tags):
    repo, created = StackExchangeRepository.objects.get_or_create(site=site, tagged=tags)
    if not repo.repo_sched:
        repo.link_sched_repo()
    repo.projects.add(project)
    analyze_stack_repo_obj(project.creator, repo.repo_sched)
    AddStackExchangeRepoAction.objects.create(creator=project.creator, project=project, repository=repo)


def analyze_data(project, site, tags):
    tags = parse_tags(tags)
    if site and tags:
        token = project.creator.stackexchangetokens.first()
        if not token:
            return {'status': 'error',
                    'message': 'Token not found for the creator of the project',
                    'code': 400}

        analyze_stackexchange(project, site, tags)
        project.update_elastic_role()

        return {'status': 'ok', 'code': 200}

    return {'status': 'error',
            'message': 'Is that a valid site or tags?',
            'code': 400}
