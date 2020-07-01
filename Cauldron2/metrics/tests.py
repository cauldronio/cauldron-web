import datetime
from io import StringIO

from django.test import TestCase
from django.utils import timezone
from django.core.management import call_command

from CauldronApp.models import User, Dashboard
from metrics import models


TODAY = timezone.now()
YESTERDAY = timezone.now() - datetime.timedelta(days=1)
PAST_MONTH = TODAY.replace(day=1) - datetime.timedelta(days=1)


TEST_DATA = {
    'users': [
        {
            'date_joined': TODAY,
            'last_login': TODAY,
            'dashboards': [
                {'created': TODAY},
                {'created': TODAY}
            ]
        },
        {
            'date_joined': YESTERDAY,
            'last_login': TODAY,
            'dashboards': [
                {'created': YESTERDAY},
                {'created': TODAY}
            ]
        },
        {
            'date_joined': YESTERDAY,
            'last_login': YESTERDAY,
            'dashboards': [
                {'created': YESTERDAY},
            ]
        },
        {
            'date_joined': PAST_MONTH,
            'last_login': PAST_MONTH,
            'dashboards': [
                {'created': PAST_MONTH},
            ]
        },
        {
            'date_joined': PAST_MONTH,
            'last_login': TODAY,
            'dashboards': [
                {'created': TODAY},
            ]
        },
        {
            'date_joined': PAST_MONTH,
            'last_login': YESTERDAY,
            'dashboards': [
                {'created': TODAY},
            ]
        }

    ]
}


class DailyMetricsTestCase(TestCase):
    def setUp(self):

        for user_id, user in enumerate(TEST_DATA['users']):
            u = User.objects.create_user(f'user_{user_id}', password='test_password')
            u.date_joined = user['date_joined']
            u.last_login = user['last_login']
            u.save()

            for dash_id, dashboard in enumerate(user['dashboards']):
                d = Dashboard.objects.create(name=f'dashboard_{dash_id}', creator=u)
                d.created = dashboard['created']
                d.save()

    def test_today_daily_metrics(self):
        out = StringIO()
        today = datetime.date.today()
        call_command('dailymetrics', save=True, no_color=True, verbosity=0, stdout=out)

        self.assertIn('Results stored in the database', out.getvalue())

        new_users = models.DailyCreatedUsers.objects.get(date=today).total
        active_users = models.DailyLoggedUsers.objects.get(date=today).total
        new_projects = models.DailyCreatedProjects.objects.get(date=today).total
        completed_tasks = models.DailyCompletedTasks.objects.get(date=today).total

        self.assertEqual(new_users, 1)
        self.assertEqual(active_users, 3)
        self.assertEqual(new_projects, 5)
        self.assertEqual(completed_tasks, 0)

    def test_yesterday_daily_metrics(self):
        out = StringIO()
        yesterday = datetime.date.today() - datetime.timedelta(days=1)
        yesterday_str = yesterday.strftime("%Y-%m-%d")
        call_command('dailymetrics', date=yesterday_str, save=True, no_color=True, verbosity=0, stdout=out)

        self.assertIn('Results stored in the database', out.getvalue())

        new_users = models.DailyCreatedUsers.objects.get(date=yesterday).total
        active_users = models.DailyLoggedUsers.objects.get(date=yesterday).total
        new_projects = models.DailyCreatedProjects.objects.get(date=yesterday).total
        completed_tasks = models.DailyCompletedTasks.objects.get(date=yesterday).total

        self.assertEqual(new_users, 2)
        self.assertEqual(active_users, 2)
        self.assertEqual(new_projects, 2)
        self.assertEqual(completed_tasks, 0)

    def test_current_month_metrics(self):
        out = StringIO()
        call_command('monthlymetrics', save=True, no_color=True, verbosity=0, stdout=out)

        self.assertIn('Results stored in the database', out.getvalue())

        new_users = models.MonthlyCreatedUsers.objects.get(date__month=TODAY.month,
                                                           date__year=TODAY.year).total
        active_users = models.MonthlyLoggedUsers.objects.get(date__month=TODAY.month,
                                                             date__year=TODAY.year).total
        new_projects = models.MonthlyCreatedProjects.objects.get(date__month=TODAY.month,
                                                                 date__year=TODAY.year).total
        completed_tasks = models.MonthlyCompletedTasks.objects.get(date__month=TODAY.month,
                                                                   date__year=TODAY.year).total
        if YESTERDAY.month == TODAY.month:
            self.assertEqual(new_users, 3)
            self.assertEqual(active_users, 5)
            self.assertEqual(new_projects, 7)
            self.assertEqual(completed_tasks, 0)
        else:
            self.assertEqual(new_users, 1)
            self.assertEqual(active_users, 3)
            self.assertEqual(new_projects, 5)
            self.assertEqual(completed_tasks, 0)

    def test_past_month_metrics(self):
        out = StringIO()
        call_command('monthlymetrics', previous_month=True, save=True, no_color=True, verbosity=0, stdout=out)

        self.assertIn('Results stored in the database', out.getvalue())

        new_users = models.MonthlyCreatedUsers.objects.get(date__month=PAST_MONTH.month,
                                                           date__year=PAST_MONTH.year).total
        active_users = models.MonthlyLoggedUsers.objects.get(date__month=PAST_MONTH.month,
                                                             date__year=PAST_MONTH.year).total
        new_projects = models.MonthlyCreatedProjects.objects.get(date__month=PAST_MONTH.month,
                                                                 date__year=PAST_MONTH.year).total
        completed_tasks = models.MonthlyCompletedTasks.objects.get(date__month=PAST_MONTH.month,
                                                                   date__year=PAST_MONTH.year).total
        if YESTERDAY.month == TODAY.month:
            self.assertEqual(new_users, 3)
            self.assertEqual(active_users, 1)
            self.assertEqual(new_projects, 1)
            self.assertEqual(completed_tasks, 0)
        else:
            self.assertEqual(new_users, 5)
            self.assertEqual(active_users, 3)
            self.assertEqual(new_projects, 3)
            self.assertEqual(completed_tasks, 0)
