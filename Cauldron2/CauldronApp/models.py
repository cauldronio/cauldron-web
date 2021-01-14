"""
The models are in another application in a new repository.
This decision was made to be able to modify the database from the workers and avoid duplicate code.
Here we import all the 'cauldron' models to make it easier to use from this repository.
"""
from cauldron_apps.cauldron.models import \
    Project, ProjectRole, AnonymousUser, UserWorkspace, \
    Repository, MeetupRepository, GitRepository, GitHubRepository, GitLabRepository, \
    OauthUser

