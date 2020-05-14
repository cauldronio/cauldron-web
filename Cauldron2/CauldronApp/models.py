from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User

# IMPORTANT: If you are going to modify any User Reference: take a look at merge_accounts in views.py

# IMPORTANT: If you are going to change the schema, you MUST modify the schema in mordred container


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
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    name = models.CharField(max_length=255)
    creator = models.ForeignKey(User,
                                on_delete=models.SET_NULL,
                                blank=True,
                                null=True)


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
