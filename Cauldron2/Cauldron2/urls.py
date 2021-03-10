"""Cauldron2 URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/2.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from CauldronApp import views, oauth
from Cauldron2 import settings

# IMPORTANT: Login paths must be defined in settings.LOGIN_REQUIRED_IGNORE_VIEW_NAMES
urlpatterns = [
    path('oauth/gitlab/<str:backend>', oauth.gitlab.start_oauth, name='gitlab_oauth'),
    path('oauth/github', oauth.github.start_oauth, name='github_oauth'),
    path('oauth/meetup', oauth.meetup.start_oauth, name='meetup_oauth'),
    path('oauth/twitter', oauth.twitter.start_oauth, name='twitter_oauth'),

    path('github-login', views.request_github_oauth, name='github_callback'),
    path('gitlab-login/<str:backend>', views.request_gitlab_oauth, name='gitlab_callback'),
    path('meetup-login', views.request_meetup_oauth, name='meetup_callback'),
    path('twitter-login', views.request_twitter_oauth, name='twitter_callback'),

    path('login', views.request_login, name='login_page'),
    path('logout', views.request_logout, name='logout_page'),
    path('delete-token', views.request_delete_token),
    path('unlink-account', views.request_unlink_account),

    path('compare', views.request_compare_projects, name="compare_projects"),
    path('compare/metrics', views.request_compare_projects_metrics, name="compare_projects_metrics"),

    path('projects', views.request_user_projects, name="user_projects"),
    path('projects/new', views.create_project, name='create_project'),

    path('project/<int:project_id>', views.request_show_project, name="show_project"),
    path('project/<int:project_id>/summary', views.request_project_summary, name="project_summary"),
    path('project/<int:project_id>/rename', views.request_rename_project, name="rename_project"),
    path('project/<int:project_id>/refresh', views.request_refresh_project, name="refresh_project"),
    path('project/<int:project_id>/metrics', views.request_project_metrics, name="project_metrics"),
    path('project/<int:project_id>/workspace', views.request_workspace, name="open_workspace"),
    path('project/<int:project_id>/delete', views.request_delete_project, name="delete_project"),
    path('project/<int:project_id>/public-kibana', views.request_public_kibana, name="open_public_kibana"),
    path('project/<int:project_id>/repositories', views.request_project_repositories, name="show_project_repos"),
    path('project/<int:project_id>/repositories/add', views.request_add_to_project, name="add_project_repos"),
    path('project/<int:project_id>/repositories/remove', views.request_remove_from_project, name="remove_project_repos"),
    path('project/<int:project_id>/ongoing-owners', views.request_ongoing_owners, name='project_ongoing_owners'),
    path('project/<int:project_id>/create-git-csv', views.request_create_git_csv, name='project_create_git_csv'),

    path('repository/<int:repo_id>/refresh', views.request_refresh_repository, name='refresh_repository'),
    path('repository/<int:repo_id>/actions', views.request_repo_actions, name='show_repository_actions'),
    path('repositories/info', views.request_repos_info),

    path('logs/<int:logs_id>', views.request_logs, name='show_logs'),

    path('admin-kibana', views.request_kibana_admin, name='kibana_admin'),

    path('projects/info', views.request_projects_info),

    path('terms/', views.terms, name="terms"),
    path('privacy/', views.privacy, name="privacy"),
    path('cookies/', views.cookies, name="cookies"),

    path('profile/', include('profile.urls')),

    path('stats/', views.stats_page, name="stats"),

    path('', views.homepage, name="homepage"),
    path('admin/', admin.site.urls),
]

if settings.HATSTALL_ENABLED:
    urlpatterns.insert(0, path('hatstall/', include('hatstall.urls')))
