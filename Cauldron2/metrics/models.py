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

