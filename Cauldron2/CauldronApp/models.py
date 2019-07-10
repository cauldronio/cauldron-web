from django.db import models
from django.contrib.auth.models import User

# IMPORTANT: If you are going to modify any User Reference: take a look at merge_accounts in views.py


class AnonymousUser(models.Model):
    # When an anonymous user creates a dashboard they are linked to a entry in this model
    # When they log in with some account this entry will be deleted so they will not be anonymous anymore
    user = models.OneToOneField(User, on_delete=models.CASCADE, unique=True)


class GithubUser(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, unique=True)
    username = models.CharField(max_length=100)
    token = models.CharField(max_length=100)
    photo = models.URLField()


class GitlabUser(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, unique=True)
    username = models.CharField(max_length=100)
    token = models.CharField(max_length=100)
    photo = models.URLField()


class Dashboard(models.Model):
    name = models.CharField(max_length=255)
    creator = models.ForeignKey(User,
                                on_delete=models.SET_NULL,
                                blank=True,
                                null=True)


class ESUser(models.Model):
    name = models.CharField(max_length=255, unique=True)
    password = models.CharField(max_length=255)
    role = models.CharField(max_length=255)
    dashboard = models.OneToOneField(Dashboard, on_delete=models.CASCADE, unique=True)
    index = models.CharField(max_length=255, blank=True, default="")


class Repository(models.Model):
    """
    Available backends: github, gitlab and git
    """
    url = models.URLField()
    backend = models.CharField(max_length=100)
    dashboards = models.ManyToManyField(Dashboard)
    index_name = models.CharField(max_length=100)


class Task(models.Model):
    """
    When a worker takes one:
    - Update the worker ID
    - Update the started date
    When a worker finishes one:
    - Create a completedTask
    - Delete this task
    """
    repository = models.OneToOneField(Repository, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    worker_id = models.CharField(max_length=255, blank=True)
    created = models.DateTimeField(auto_now_add=True)
    started = models.DateTimeField(null=True)
    log_file = models.CharField(max_length=255, blank=True)
    rate_time = models.DateTimeField(null=True, auto_now_add=True)


class CompletedTask(models.Model):
    task_id = models.IntegerField()
    repository = models.ForeignKey(Repository, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, blank=True, null=True)
    created = models.DateTimeField()
    started = models.DateTimeField()
    completed = models.DateTimeField()
    status = models.CharField(max_length=255)
    log_file = models.CharField(max_length=255, blank=True)
