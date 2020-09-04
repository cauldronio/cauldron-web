from django.db import models
from django.utils import timezone

# from CauldronApp.models import Project

from poolsched import models as sched_models
from poolsched import api as sched_api

from model_utils.managers import InheritanceManager

import logging


class Repository(models.Model):
    GIT = 'GI'
    GITHUB = 'GH'
    GITLAB = 'GL'
    MEETUP = 'MU'
    UNKNOWN = 'UK'
    BACKEND_CHOICES = [
        (GIT, 'Git'),
        (GITHUB, 'GitHub'),
        (GITLAB, 'GitLab'),
        (MEETUP, 'Meetup'),
    ]
    # Globals for the state of a repository
    IN_PROGRESS = 'In progress'
    ANALYZED = 'Analyzed'
    ERROR = 'Error'

    objects = InheritanceManager()

    projects = models.ManyToManyField('CauldronApp.project')
    backend = models.CharField(
        max_length=2,
        choices=BACKEND_CHOICES,
        default=UNKNOWN,
    )

    def __str__(self):
        return f"{self.pk} - {self.get_backend_display()}"

    @property
    def status(self):
        """Return running, pending or unknown depending on the status"""
        raise NotImplementedError

    @property
    def last_refresh(self):
        """Return the last refresh of the repository, Raw + Enrich"""
        raise NotImplementedError


class GitRepository(Repository):
    url = models.CharField(max_length=255, unique=True)
    parent = models.OneToOneField(to=Repository, on_delete=models.CASCADE, parent_link=True, related_name='git')
    repo_sched = models.OneToOneField(sched_models.GitRepo, on_delete=models.SET_NULL, null=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.backend = Repository.GIT

    def __str__(self):
        return f"{self.pk} - ...{self.url[-20:]}"

    def link_sched_repo(self):
        if not self.repo_sched:
            repo_sched, _ = sched_models.GitRepo.objects.get_or_create(url=self.url)
            self.repo_sched = repo_sched
            self.save()

    def as_url(self):
        return self.url

    def refresh(self, user):
        sched_api.analyze_git_repo_obj(user, self.repo_sched)

    @property
    def status(self):
        """Return status of the repository"""
        intentions = self.repo_sched.igitraw_set.count() + self.repo_sched.igitenrich_set.count()
        if intentions > 0:
            return self.IN_PROGRESS
        try:
            enrich = self.repo_sched.igitenricharchived_set\
                .latest('completed')
            raw = self.repo_sched.igitrawarchived_set\
                .latest('completed')
            ok = (enrich.status == sched_models.ArchivedIntention.OK) and \
                 (raw.status == sched_models.ArchivedIntention.OK)
        except sched_models.IGitEnrichArchived.DoesNotExist:
            ok = False

        if ok:
            return self.ANALYZED
        else:
            return self.ERROR

    @property
    def last_refresh(self):
        try:
            date = sched_models.IGitEnrichArchived.objects.filter(repo=self.repo_sched).latest('completed').completed
        except sched_models.IGitEnrichArchived.DoesNotExist:
            date = 'Not analyzed'
        return date


class GitHubRepository(Repository):
    owner = models.CharField(max_length=40)
    repo = models.CharField(max_length=100)
    parent = models.OneToOneField(to=Repository, on_delete=models.CASCADE, parent_link=True, related_name='github')
    repo_sched = models.OneToOneField(sched_models.GHRepo, on_delete=models.SET_NULL, null=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.backend = Repository.GITHUB

    def __str__(self):
        return f"{self.pk} - {self.owner}/{self.repo}"

    def link_sched_repo(self):
        if not self.repo_sched:
            instance = sched_models.GHInstance.objects.get(name='GitHub')
            repo_sched, _ = sched_models.GHRepo.objects.get_or_create(owner=self.owner, repo=self.repo,
                                                                      instance=instance)
            self.repo_sched = repo_sched
            self.save()

    def as_url(self):
        return f"https://github.com/{self.owner}/{self.repo}"

    def refresh(self, user):
        sched_api.analyze_gh_repo_obj(user, self.repo_sched)

    @property
    def status(self):
        """Return status of the repository"""
        intentions = self.repo_sched.ighraw_set.count() + self.repo_sched.ighenrich_set.count()
        if intentions > 0:
            return self.IN_PROGRESS
        try:
            enrich = self.repo_sched.ighenricharchived_set\
                .latest('completed')
            raw = self.repo_sched.ighrawarchived_set\
                .latest('completed')
            ok = (enrich.status == sched_models.ArchivedIntention.OK) and \
                 (raw.status == sched_models.ArchivedIntention.OK)
        except sched_models.IGHEnrichArchived.DoesNotExist:
            ok = False

        if ok:
            return self.ANALYZED
        else:
            return self.ERROR

    @property
    def last_refresh(self):
        try:
            date = sched_models.IGHEnrichArchived.objects.filter(repo=self.repo_sched).latest('completed').completed
        except sched_models.IGHEnrichArchived.DoesNotExist:
            date = 'Not analyzed'
        return date


class GitLabRepository(Repository):
    owner = models.CharField(max_length=40)
    repo = models.CharField(max_length=100)
    parent = models.OneToOneField(to=Repository, on_delete=models.CASCADE, parent_link=True, related_name='gitlab')
    repo_sched = models.OneToOneField(sched_models.GLRepo, on_delete=models.SET_NULL, null=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.backend = Repository.GITLAB

    def __str__(self):
        return f"{self.pk} - {self.owner}/{self.repo}"

    def link_sched_repo(self):
        if not self.repo_sched:
            instance = sched_models.GLInstance.objects.get(name='GitLab')
            repo_sched, _ = sched_models.GLRepo.objects.get_or_create(owner=self.owner, repo=self.repo,
                                                                      instance=instance)
            self.repo_sched = repo_sched
            self.save()

    def as_url(self):
        return f"https://gitlab.com/{self.owner}/{self.repo}"

    def refresh(self, user):
        sched_api.analyze_gl_repo_obj(user, self.repo_sched)

    @property
    def status(self):
        """Return status of the repository"""
        intentions = self.repo_sched.iglraw_set.count() + self.repo_sched.iglenrich_set.count()
        if intentions > 0:
            return self.IN_PROGRESS
        try:
            enrich = self.repo_sched.iglenricharchived_set\
                .latest('completed')
            raw = self.repo_sched.iglrawarchived_set\
                .latest('completed')
            ok = (enrich.status == sched_models.ArchivedIntention.OK) and \
                 (raw.status == sched_models.ArchivedIntention.OK)
        except sched_models.IGLEnrichArchived.DoesNotExist:
            ok = False

        if ok:
            return self.ANALYZED
        else:
            return self.ERROR


    @property
    def last_refresh(self):
        try:
            date = sched_models.IGLEnrichArchived.objects.filter(repo=self.repo_sched).latest('completed').completed
        except sched_models.IGLEnrichArchived.DoesNotExist:
            date = 'Not analyzed'
        return date


class MeetupRepository(Repository):
    group = models.CharField(max_length=100)
    parent = models.OneToOneField(to=Repository, on_delete=models.CASCADE, parent_link=True, related_name='meetup')
    repo_sched = models.OneToOneField(sched_models.MeetupRepo, on_delete=models.SET_NULL, null=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.backend = Repository.MEETUP

    def __str__(self):
        return f"{self.pk} - {self.group}"

    def link_sched_repo(self):
        if not self.repo_sched:
            repo_sched, _ = sched_models.MeetupRepo.objects.get_or_create(group=self.group)
            self.repo_sched = repo_sched
            self.save()

    def as_url(self):
        return self.group

    def refresh(self, user):
        sched_api.analyze_meetup_repo_obj(user, self.repo_sched)

    @property
    def status(self):
        """Return status of the repository"""
        intentions = self.repo_sched.imeetupraw_set.count() + self.repo_sched.imeetupenrich_set.count()
        if intentions > 0:
            return self.IN_PROGRESS
        try:
            enrich = self.repo_sched.imeetupenricharchived_set \
                .latest('completed')
            raw = self.repo_sched.imeetuprawarchived_set \
                .latest('completed')
            ok = (enrich.status == sched_models.ArchivedIntention.OK) and \
                 (raw.status == sched_models.ArchivedIntention.OK)
        except sched_models.IMeetupEnrichArchived.DoesNotExist:
            ok = False

        if ok:
            return self.ANALYZED
        else:
            return self.ERROR

    @property
    def last_refresh(self):
        try:
            date = sched_models.IMeetupEnrichArchived.objects.filter(repo=self.repo_sched).latest('completed').completed
        except sched_models.IMeetupEnrichArchived.DoesNotExist:
            date = 'Not analyzed'
        return date

