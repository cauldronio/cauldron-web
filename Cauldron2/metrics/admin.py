from django.contrib import admin
from metrics import models


@admin.register(models.DailyCreatedUsers,
                models.DailyLoggedUsers,
                models.DailyCreatedProjects,
                models.DailyCompletedTasks,
                models.DailyProjectsPerUser,
                models.DailyActivatedUsers,
                models.DailyRealUsers,
                models.DailyM2,
                models.DailyM3,
                models.BiweeklyCreatedUsers,
                models.BiweeklyLoggedUsers,
                models.BiweeklyCreatedProjects,
                models.BiweeklyCompletedTasks,
                models.BiweeklyProjectsPerUser,
                models.BiweeklyActivatedUsers,
                models.BiweeklyRealUsers,
                models.BiweeklyM2,
                models.BiweeklyM3,
                models.MonthlyCreatedUsers,
                models.MonthlyLoggedUsers,
                models.MonthlyCreatedProjects,
                models.MonthlyCompletedTasks,
                models.MonthlyProjectsPerUser,
                models.MonthlyActivatedUsers,
                models.MonthlyRealUsers,
                models.MonthlyM2,
                models.MonthlyM3)

class CommonAdmin(admin.ModelAdmin):
    date_hierarchy = 'date'
    list_display = ('date', 'total')
