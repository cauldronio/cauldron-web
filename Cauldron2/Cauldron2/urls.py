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
from CauldronApp import views
from Cauldron2 import settings

urlpatterns = [
    path('github-login', views.request_github_oauth),
    path('gitlab-login', views.request_gitlab_oauth),
    path('meetup-login', views.request_meetup_oauth),
    path('logout', views.request_logout),
    path('delete-token', views.request_delete_token),

    path('compare', views.request_compare_projects, name="compare_projects"),

    path('projects', views.request_user_projects, name="user_projects"),

    path('project', views.request_new_project, name='new_project'),
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

    path('repository/<int:repo_id>/refresh', views.request_refresh_repository, name='refresh_repository'),
    path('repository/<int:repo_id>/actions', views.request_repo_actions, name='show_repository_actions'),
    path('repositories/info', views.request_repos_info),

    path('logs/<int:logs_id>', views.request_logs, name='show_logs'),

    path('admin-kibana', views.request_kibana_admin, name='kibana_admin'),

    path('projects/info', views.request_projects_info),

    path('terms/', views.terms, name="terms"),
    path('privacy/', views.privacy, name="privacy"),
    path('cookies/', views.cookies, name="cookies"),

    # path('admin-page/', views.admin_page, name="admin_page"),
    # path('admin-page/users/', views.admin_page_users, name="admin_page_users"),
    # path('admin-page/users/upgrade/', views.upgrade_user, name="upgrade_user"),
    # path('admin-page/users/downgrade/', views.downgrade_user, name="downgrade_user"),
    # path('admin-page/users/delete/', views.request_delete_user, name="delete_user"),
    path('profile/', include('profile.urls')),

    path('stats/', views.stats_page, name="stats"),

    path('', views.homepage, name="homepage"),
    path('admin/', admin.site.urls),
]

if settings.HATSTALL_ENABLED:
    urlpatterns.insert(0, path('hatstall/', include('hatstall.urls')))
