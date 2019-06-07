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
from django.urls import path
from CauldronApp import views

urlpatterns = [
    path('github-login', views.request_github_login_callback),
    path('gitlab-login', views.request_gitlab_login_callback),
    path('logout', views.request_logout),
    path('delete-token', views.request_delete_token),

    path('new-dashboard', views.request_new_dashboard),
    path('dashboard/<int:dash_id>/edit', views.request_edit_dashboard),
    path('dashboard/<int:dash_id>', views.request_show_dashboard),
    path('dashboard/<int:dash_id>/create-panels', views.request_import_panels),

    path('dashboard-status/<slug:dash_name>', views.dash_status),
    path('dashboard-info/<int:dash_id>', views.request_dash_info),
    path('repo-logs/<int:repo_id>', views.repo_logs),

    path('kibana/<int:dash_id>', views.request_kibana),

    path('', views.homepage),
    # path('admin/', admin.site.urls),

]
