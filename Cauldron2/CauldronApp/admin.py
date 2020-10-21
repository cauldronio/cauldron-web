from django.contrib import admin
from CauldronApp import models


# Register your models here.
@admin.register(models.Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'created', 'creator_name')
    list_filter = ('created', 'creator__first_name')
    search_fields = ('id', 'name', 'creator__first_name')
    ordering = ('id',)

    def creator_name(self, obj):
        try:
            return obj.creator.first_name
        except AttributeError:
            return None


@admin.register(models.Repository)
class RepositoryAdmin(admin.ModelAdmin):
    list_display = ('id', 'backend')
    list_filter = ('backend',)
    ordering = ('id',)


@admin.register(models.GitRepository)
class GitRepositoryAdmin(admin.ModelAdmin):
    list_display = ('id', 'url', 'repo_sched', 'status', 'last_refresh')
    search_fields = ('id', 'url')
    ordering = ('id',)


@admin.register(models.GitHubRepository)
class GitHubRepositoryAdmin(admin.ModelAdmin):
    list_display = ('id', 'owner', 'repo', 'repo_sched', 'status', 'last_refresh')
    search_fields = ('id', 'owner', 'repo')
    ordering = ('id', )


@admin.register(models.GitLabRepository)
class GitLabRepositoryAdmin(admin.ModelAdmin):
    list_display = ('id', 'owner', 'repo', 'repo_sched', 'status', 'last_refresh')
    search_fields = ('id', 'owner', 'repo')
    ordering = ('id', )


@admin.register(models.MeetupRepository)
class MeetupRepositoryAdmin(admin.ModelAdmin):
    list_display = ('id', 'group', 'repo_sched', 'status', 'last_refresh')
    search_fields = ('id', 'group')
    ordering = ('id',)


@admin.register(models.UserWorkspace)
class UserWorkspaceAdmin(admin.ModelAdmin):
    list_display = ('id', 'user_name', 'tenant_name', 'tenant_role', 'backend_role')
    search_fields = ('id', 'user__first_name', 'tenant_name')
    ordering = ('id',)

    def user_name(self, obj):
        try:
            return obj.user.first_name
        except AttributeError:
            return None


@admin.register(models.ProjectRole)
class ProjectRoleAdmin(admin.ModelAdmin):
    list_display = ('id', 'role', 'backend_role', 'project')
    ordering = ('id',)


admin.site.register(models.AnonymousUser)
