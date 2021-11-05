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
    path('oauth/stackexchange', oauth.stackexchange.start_oauth, name='stack_oauth'),

    path('github-login', views.request_github_oauth, name='github_callback'),
    path('gitlab-login/<str:backend>', views.request_gitlab_oauth, name='gitlab_callback'),
    path('meetup-login', views.request_meetup_oauth, name='meetup_callback'),
    path('twitter-login', views.request_twitter_oauth, name='twitter_callback'),
    path('stackexchange-login', views.request_stack_oauth, name='stackexchange_callback'),

    path('login', views.request_login, name='login_page'),
    path('logout', views.request_logout, name='logout_page'),
    path('delete-token', views.request_delete_token),
    path('unlink-account', views.request_unlink_account),

    path('compare', views.request_compare_projects, name="compare_projects"),
    path('compare/metrics', views.request_compare_projects_metrics, name="compare_projects_metrics"),

    path('projects', views.request_user_projects, name="user_projects"),
    path('projects/new', views.create_project, name='create_project'),

    path('explore', views.request_explore_projects, name="explore_projects"),

    path('project/<int:project_id>', views.request_show_project, name="show_project"),
    path('project/<int:project_id>/summary', views.request_project_summary, name="project_summary"),
    path('project/<int:project_id>/rename', views.request_rename_project, name="rename_project"),
    path('project/<int:project_id>/refresh', views.request_refresh_project, name="refresh_project"),
    path('project/<int:project_id>/metrics', views.request_project_metrics, name="project_metrics"),
    path('project/<int:project_id>/workspace', views.request_workspace, name="open_workspace"),
    path('project/<int:project_id>/delete', views.request_delete_project, name="delete_project"),
    path('project/<int:project_id>/fork', views.request_project_fork, name='fork_project'),
    path('project/<int:project_id>/public-kibana', views.request_public_kibana, name="open_public_kibana"),
    path('project/<int:project_id>/repositories', views.request_project_repositories, name="show_project_repos"),
    path('project/<int:project_id>/settings', views.request_project_actions, name="show_project_actions"),
    path('project/<int:project_id>/settings/visibility', views.request_report_visibility, name="show_project_visibility"),
    path('project/<int:project_id>/settings/autorefresh', views.request_project_autorefresh, name='request_project_autorefresh'),
    path('project/<int:project_id>/actions/refresh', views.request_project_actions_refresh, name="refresh_project_actions"),
    path('project/<int:project_id>/actions/remove', views.request_project_actions_remove, name="remove_project_actions"),
    path('project/<int:project_id>/repositories/add', views.request_add_to_project, name="add_project_repos"),
    path('project/<int:project_id>/repositories/remove', views.request_remove_from_project, name="remove_project_repos"),
    path('project/<int:project_id>/ongoing-owners', views.request_ongoing_owners, name='project_ongoing_owners'),
    path('project/<int:project_id>/export', views.request_project_export, name='project_export'),
    path('project/<int:project_id>/export/create', views.request_project_export_create, name='project_export_create'),
    path('project/<int:project_id>/export/status', views.request_project_export_status, name='project_export_status'),
    path('project/<int:project_id>/stats.svg', views.request_project_stats_svg, name='project_stats_svg'),
    path('project/<int:project_id>/git_contributors.svg', views.request_project_git_contributors_svg, name='project_git_contributors_svg'),
    path('project/<int:project_id>/export/svg/<slug:metric_name>.svg', views.request_project_export_svg, name='request_project_export_svg'),
    path('project/<int:project_id>/printable-report', views.request_project_kibana_report, name='request_printable_report'),

    path('repository/<int:repo_id>/refresh', views.request_refresh_repository, name='refresh_repository'),
    path('repository/<int:repo_id>/actions', views.request_repo_intentions, name='show_repository_intentions'),
    path('repositories/info', views.request_repos_info),

    path('logs/<int:logs_id>', views.request_logs, name='show_logs'),

    path('admin-kibana', views.request_kibana_admin, name='kibana_admin'),

    path('projects/info', views.request_projects_info),
    path('projects/commits-by-week', views.request_commits_by_week, name='commits_by_week'),

    path('message/<int:message_id>/dismiss', views.request_dismiss_message, name='dismiss_message'),

    path('terms/', views.terms, name="terms"),
    path('privacy/', views.privacy, name="privacy"),
    path('cookies/', views.cookies, name="cookies"),
    path('pricing/', views.pricing, name="pricing"),

    path('users/', views.admin_page_users, name="admin_page_users"),
    path('users/authorize/', views.authorize_user, name="authorize_user"),
    path('users/unauthorize/', views.unauthorize_user, name="unauthorize_user"),
    path('users/upgrade/', views.upgrade_user, name="upgrade_user"),
    path('users/downgrade/', views.downgrade_user, name="downgrade_user"),
    path('users/add', views.request_add_user, name="add_user"),
    path('users/delete/', views.request_delete_user, name="delete_user"),

    path('profile/', include('profile.urls')),

    path('stats/', views.stats_page, name="stats"),

    path('', views.homepage, name="homepage"),
    path('admin/', admin.site.urls),
]

if settings.SPDX_ENABLED:
    urlpatterns.append(path('sbom/new', views.request_create_sbom, name='create_sbom'))
    urlpatterns.append(path('spdx/results/<int:spdx_id>', views.request_spdx_results, name='spdx_results'))

if settings.HATSTALL_ENABLED:
    urlpatterns.insert(0, path('hatstall/', include('hatstall.urls')))
