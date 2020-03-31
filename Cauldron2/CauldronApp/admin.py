from django.contrib import admin
from CauldronApp import models

# Register your models here.

admin.site.register(models.GithubUser)
admin.site.register(models.GitlabUser)
admin.site.register(models.Dashboard)
admin.site.register(models.Repository)
admin.site.register(models.Task)
admin.site.register(models.CompletedTask)
admin.site.register(models.AnonymousUser)
admin.site.register(models.ProjectRole)
admin.site.register(models.UserWorkspace)
admin.site.register(models.Token)
