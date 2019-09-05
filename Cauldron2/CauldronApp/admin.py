from django.contrib import admin
from CauldronApp.models import GithubUser, GitlabUser, Dashboard, Repository, Task, CompletedTask, AnonymousUser, ESUser, Token

# Register your models here.

admin.site.register(GithubUser)
admin.site.register(GitlabUser)
admin.site.register(Dashboard)
admin.site.register(Repository)
admin.site.register(Task)
admin.site.register(CompletedTask)
admin.site.register(AnonymousUser)
admin.site.register(ESUser)
admin.site.register(Token)
