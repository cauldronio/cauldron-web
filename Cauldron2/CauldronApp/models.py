from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User

from datetime import datetime, timedelta
import pytz

# IMPORTANT: If you are going to modify any User Reference: take a look at merge_accounts in views.py

# IMPORTANT: If you are going to change the schema, you MUST modify the schema in worker container


class AnonymousUser(models.Model):
    # When an anonymous user creates a dashboard they are linked to a entry in this model
    # When they log in with some account this entry will be deleted so they will not be anonymous anymore
    user = models.OneToOneField(User, on_delete=models.CASCADE, unique=True)


class UserWorkspace(models.Model):
    """
    This field indicates if the user has created the workspace
    in Kibana and the name
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE, unique=True)
    tenant_name = models.CharField(max_length=100)
    tenant_role = models.CharField(max_length=100)
    backend_role = models.CharField(max_length=100)


class Token(models.Model):
    STATUS_READY = 'ready'
    STATUS_COOLDOWN = 'cooldown'

    backend = models.CharField(max_length=100)
    key = models.CharField(max_length=200)
    rate_time = models.DateTimeField(null=True, auto_now_add=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE)

    @property
    def status(self):
        if self.rate_time <= timezone.now():
            return self.STATUS_READY

        return self.STATUS_COOLDOWN

    def is_ready(self):
        return self.status == self.STATUS_READY


class GithubUser(models.Model):
    BACKEND_NAME = 'github'
    user = models.OneToOneField(User, on_delete=models.CASCADE, unique=True)
    username = models.CharField(max_length=100)
    token = models.ForeignKey(Token, on_delete=models.CASCADE)
    photo = models.URLField()


class GitlabUser(models.Model):
    BACKEND_NAME = 'gitlab'
    user = models.OneToOneField(User, on_delete=models.CASCADE, unique=True)
    username = models.CharField(max_length=100)
    token = models.ForeignKey(Token, on_delete=models.CASCADE)
    photo = models.URLField()


class MeetupUser(models.Model):
    BACKEND_NAME = 'meetup'
    user = models.OneToOneField(User, on_delete=models.CASCADE, unique=True)
    username = models.CharField(max_length=100)
    token = models.ForeignKey(Token, on_delete=models.CASCADE)
    refresh_token = models.CharField(max_length=100)
    photo = models.URLField()


class Dashboard(models.Model):
    SORT_CHOICES = [
        'name',
        '-name',
        'owner',
        '-owner',
        'created',
        '-created',
        'modified',
        '-modified',
        'total_tasks',
        '-total_tasks',
        'completed_tasks',
        '-completed_tasks',
        'running_tasks',
        '-running_tasks',
        'pending_tasks',
        '-pending_tasks',
        'error_tasks',
        '-error_tasks',
        'total_repositories',
        '-total_repositories',
        'git',
        '-git',
        'github',
        '-github',
        'gitlab',
        '-gitlab',
        'meetup',
        '-meetup',
    ]

    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    name = models.CharField(max_length=255)
    creator = models.ForeignKey(User,
                                on_delete=models.SET_NULL,
                                blank=True,
                                null=True)

    @property
    def tasks_count(self):
        repos = self.repository_set.all()
        return CompletedTask.objects.filter(repository__in=repos, old=False).count() + \
                Task.objects.filter(repository__in=repos).count()

    @property
    def completed_tasks_count(self):
        repos = self.repository_set.all()
        return CompletedTask.objects.filter(repository__in=repos,
                                            status="COMPLETED",
                                            old=False).count()

    @property
    def running_tasks_count(self):
        repos = self.repository_set.all()
        return Task.objects.filter(repository__in=repos).exclude(worker_id="").count()

    @property
    def pending_tasks_count(self):
        repos = self.repository_set.all()
        return Task.objects.filter(repository__in=repos, worker_id="").count()

    @property
    def error_tasks_count(self):
        repos = self.repository_set.all()
        return CompletedTask.objects.filter(repository__in=repos,
                                            status="ERROR",
                                            old=False).count()

    @property
    def repos_count(self):
        return self.repository_set.count()

    @property
    def repos_git_count(self):
        return self.repository_set.filter(backend="git").count()

    @property
    def repos_github_count(self):
        return self.repository_set.filter(backend="github").count()

    @property
    def repos_gitlab_count(self):
        return self.repository_set.filter(backend="gitlab").count()

    @property
    def repos_meetup_count(self):
        return self.repository_set.filter(backend="meetup").count()

    @property
    def last_refresh(self):
        if self.repos_count == 0:
            return datetime.now(pytz.utc)

        return sorted(self.repository_set.all(), key=lambda r: r.last_refresh)[0].last_refresh

    @property
    def is_outdated(self):
        elapsed_time = datetime.now(pytz.utc) - self.last_refresh
        return elapsed_time > timedelta(days=5)


class ProjectRole(models.Model):
    role = models.CharField(max_length=255, unique=True)
    backend_role = models.CharField(max_length=255, unique=True)
    dashboard = models.OneToOneField(Dashboard, on_delete=models.CASCADE, unique=True)


class Repository(models.Model):
    """
    Available backends: github, gitlab, meetup and git
    """
    BACKEND_CHOICES = [
        'git',
        'github',
        'gitlab',
        'meetup',
    ]

    STATUS_CHOICES = [
        'completed',
        'running',
        'pending',
        'error',
        'unknown',
    ]

    SORT_CHOICES = [
        'status',
        '-status',
        'kind',
        '-kind',
        'refresh',
        '-refresh',
        'duration',
        '-duration',
    ]

    url = models.URLField()
    backend = models.CharField(max_length=100)
    dashboards = models.ManyToManyField(Dashboard)

    @property
    def status(self):
        try:
            task = Task.objects.get(repository=self)
            if task.worker_id:
                return 'running'
            else:
                return 'pending'
        except Task.DoesNotExist:
            try:
                c_task = CompletedTask.objects.get(repository=self, old=False)
                return c_task.status.lower()
            except CompletedTask.DoesNotExist:
                return 'unknown'

    @property
    def last_refresh(self):
        try:
            c_task = CompletedTask.objects.get(repository=self, old=False)
            return c_task.completed
        except CompletedTask.DoesNotExist:
            return timezone.now()

    @property
    def duration(self):
        started = completed = timezone.now()

        try:
            task = Task.objects.get(repository=self)

            # If the status is different from 'running', it will
            # return a zero value for this field
            if self.status == 'running':
                started = task.started
                completed = timezone.now()

        except Task.DoesNotExist:
            try:
                c_task = CompletedTask.objects.get(repository=self, old=False)

                started = c_task.started
                completed = c_task.completed
            except CompletedTask.DoesNotExist:
                pass

        return (completed - started).total_seconds()


class Task(models.Model):
    """
    When a worker takes one:
    - Update the worker ID
    - Update the started date
    When a worker finishes one:
    - Create a completedTask
    - Delete this task
    """
    repository = models.ForeignKey(Repository, on_delete=models.CASCADE)
    worker_id = models.CharField(max_length=255, blank=True)
    created = models.DateTimeField(auto_now_add=True)
    started = models.DateTimeField(null=True)
    retries = models.IntegerField(default=0)
    log_file = models.CharField(max_length=255, blank=True)
    tokens = models.ManyToManyField(Token)


class CompletedTask(models.Model):
    task_id = models.IntegerField()
    repository = models.ForeignKey(Repository, on_delete=models.CASCADE)
    created = models.DateTimeField()
    started = models.DateTimeField()
    completed = models.DateTimeField()
    retries = models.IntegerField()
    status = models.CharField(max_length=255)
    log_file = models.CharField(max_length=255, blank=True)
    old = models.BooleanField(default=False)


class SHTask(models.Model):
    # MUST BE UTC DATE
    scheduled_date = models.DateTimeField()
    started_date = models.DateTimeField(null=True)
    completed_date = models.DateTimeField(null=True)
    done = models.BooleanField(default=False)
    log_file = models.CharField(max_length=255, blank=True)
