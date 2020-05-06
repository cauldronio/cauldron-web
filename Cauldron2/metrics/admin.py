from django.contrib import admin
from metrics import models


@admin.register(models.DailyCreatedUsers,
                models.DailyLoggedUsers,
                models.DailyCreatedProjects,
                models.DailyCompletedTasks,
                models.MonthlyCreatedUsers,
                models.MonthlyLoggedUsers,
                models.MonthlyCreatedProjects,
                models.MonthlyCompletedTasks)
class CommonAdmin(admin.ModelAdmin):
    date_hierarchy = 'date'
    list_display = ('date', 'total')

