from django.urls import path
from . import views


app_name = 'profile'
urlpatterns = [
    path('', views.index, name='index'),
    path('delete/', views.request_delete_own_user, name="delete_user"),
]
