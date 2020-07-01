from django.db import models
import datetime


class DailyCreatedUsers(models.Model):
    date = models.DateField(unique=True)
    total = models.IntegerField()

    class Meta:
        verbose_name_plural = 'Daily Created Users'


class DailyLoggedUsers(models.Model):
    date = models.DateField(unique=True)
    total = models.IntegerField()

    class Meta:
        verbose_name_plural = 'Daily Logged Users'


class DailyCreatedProjects(models.Model):
    date = models.DateField(unique=True)
    total = models.IntegerField()

    class Meta:
        verbose_name_plural = 'Daily Created Projects'


class DailyCompletedTasks(models.Model):
    date = models.DateField(unique=True)
    total = models.IntegerField()

    class Meta:
        verbose_name_plural = 'Daily Completed Tasks'


class DailyProjectsPerUser(models.Model):
    date = models.DateField(unique=True)
    total = models.IntegerField()

    class Meta:
        verbose_name_plural = 'Daily Projects per User'


class DailyActivatedUsers(models.Model):
    date = models.DateField(unique=True)
    total = models.IntegerField()

    class Meta:
        verbose_name_plural = 'Daily Activated Users'


class DailyRealUsers(models.Model):
    date = models.DateField(unique=True)
    total = models.IntegerField()

    class Meta:
        verbose_name_plural = 'Daily Real Users'


class DailyM2(models.Model):
    date = models.DateField(unique=True)
    total = models.IntegerField()

    class Meta:
        verbose_name_plural = 'Daily M2'


class DailyM3(models.Model):
    date = models.DateField(unique=True)
    total = models.IntegerField()

    class Meta:
        verbose_name_plural = 'Daily M3'


class BiweeklyCreatedUsers(models.Model):
    date = models.DateField(unique=True)
    total = models.IntegerField()

    class Meta:
        verbose_name_plural = 'Biweekly Created Users'


class BiweeklyLoggedUsers(models.Model):
    date = models.DateField(unique=True)
    total = models.IntegerField()

    class Meta:
        verbose_name_plural = 'Biweekly Logged Users'


class BiweeklyCreatedProjects(models.Model):
    date = models.DateField(unique=True)
    total = models.IntegerField()

    class Meta:
        verbose_name_plural = 'Biweekly Created Projects'


class BiweeklyCompletedTasks(models.Model):
    date = models.DateField(unique=True)
    total = models.IntegerField()

    class Meta:
        verbose_name_plural = 'Biweekly Completed Tasks'


class BiweeklyProjectsPerUser(models.Model):
    date = models.DateField(unique=True)
    total = models.IntegerField()

    class Meta:
        verbose_name_plural = 'Biweekly Projects per User'


class BiweeklyActivatedUsers(models.Model):
    date = models.DateField(unique=True)
    total = models.IntegerField()

    class Meta:
        verbose_name_plural = 'Biweekly Activated Users'


class BiweeklyRealUsers(models.Model):
    date = models.DateField(unique=True)
    total = models.IntegerField()

    class Meta:
        verbose_name_plural = 'Biweekly Real Users'


class BiweeklyM2(models.Model):
    date = models.DateField(unique=True)
    total = models.IntegerField()

    class Meta:
        verbose_name_plural = 'Biweekly M2'


class BiweeklyM3(models.Model):
    date = models.DateField(unique=True)
    total = models.IntegerField()

    class Meta:
        verbose_name_plural = 'Biweekly M3'


class MonthlyCreatedUsers(models.Model):
    date = models.DateField(unique=True)
    total = models.IntegerField()

    class Meta:
        verbose_name_plural = 'Monthly Created Users'


class MonthlyLoggedUsers(models.Model):
    date = models.DateField(unique=True)
    total = models.IntegerField()

    class Meta:
        verbose_name_plural = 'Monthly Logged Users'


class MonthlyCreatedProjects(models.Model):
    date = models.DateField(unique=True)
    total = models.IntegerField()

    class Meta:
        verbose_name_plural = 'Monthly Created Projects'


class MonthlyCompletedTasks(models.Model):
    date = models.DateField(unique=True)
    total = models.IntegerField()

    class Meta:
        verbose_name_plural = 'Monthly Completed Tasks'


class MonthlyProjectsPerUser(models.Model):
    date = models.DateField(unique=True)
    total = models.IntegerField()

    class Meta:
        verbose_name_plural = 'Monthly Projects per User'


class MonthlyActivatedUsers(models.Model):
    date = models.DateField(unique=True)
    total = models.IntegerField()

    class Meta:
        verbose_name_plural = 'Monthly Activated Users'


class MonthlyRealUsers(models.Model):
    date = models.DateField(unique=True)
    total = models.IntegerField()

    class Meta:
        verbose_name_plural = 'Monthly Real Users'


class MonthlyM2(models.Model):
    date = models.DateField(unique=True)
    total = models.IntegerField()

    class Meta:
        verbose_name_plural = 'Monthly M2'


class MonthlyM3(models.Model):
    date = models.DateField(unique=True)
    total = models.IntegerField()

    class Meta:
        verbose_name_plural = 'Monthly M3'
