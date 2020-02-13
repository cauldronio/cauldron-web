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
    path('github-login', views.request_github_login_callback),
    path('gitlab-login', views.request_gitlab_login_callback),
    path('meetup-login', views.request_meetup_login_callback),
    path('logout', views.request_logout),
    path('delete-token', views.request_delete_token),

    path('projects', views.request_user_projects, name="projectspage"),

    path('dashboard', views.request_new_dashboard),
    path('dashboard/<int:dash_id>', views.request_show_dashboard, name="show_dashboard"),
    path('dashboard/<int:dash_id>/edit', views.request_edit_dashboard),
    path('dashboard/<int:dash_id>/edit-name', views.request_edit_dashboard_name),
    path('dashboard/<int:dash_id>/info', views.request_dash_info),
    path('dashboard/<int:dash_id>/summary', views.request_dash_summary),
    path('dashboard/<int:dash_id>/kibana', views.request_kibana, name="open_kibana"),
    path('dashboard/<int:dash_id>/delete', views.request_delete_dashboard, name="delete_project_url"),
    path('dashboard/<int:dash_id>/public-kibana', views.request_public_kibana, name="open_public_kibana"),

    path('terms/', views.terms, name="terms"),
    path('privacy/', views.privacy, name="privacy"),
    path('cookies/', views.cookies, name="cookies"),

    path('repo-logs/<int:repo_id>', views.repo_logs),

    path('admin-page/', views.admin_page, name="admin_page"),
    path('admin-page/users/', views.admin_page_users, name="admin_page_users"),
    path('admin-page/users/upgrade/', views.upgrade_user, name="upgrade_user"),
    path('admin-page/users/downgrade/', views.downgrade_user, name="downgrade_user"),
    path('admin-page/users/delete/', views.request_delete_user, name="delete_user"),
    path('profile/', include('profile.urls')),

    path('status/', views.status_page, name="status"),

    path('', views.homepage, name="homepage"),
    path('admin/', admin.site.urls),
]

if settings.HATSTALL_ENABLED:
    urlpatterns.insert(0, path('hatstall/', include('hatstall.urls')))
