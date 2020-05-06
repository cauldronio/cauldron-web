from django.core.management.base import BaseCommand
from CauldronApp.models import User, Dashboard, CompletedTask
from metrics import models

import datetime


class Command(BaseCommand):
    help = 'Collect metrics related to Cauldron from the current day.'

    def add_arguments(self, parser):
        parser.add_argument(
            '-s',
            '--save',
            action='store_true',
            help="store results in database"
        )

        parser.add_argument(
            '--date',
            type=lambda s: datetime.datetime.strptime(s, '%Y-%m-%d').date(),
            help="metrics from a specific day (YYYY-MM-DD)"
        )

    def handle(self, *args, **options):
        if options['date']:
            date_metrics = options['date']
        else:
            date_metrics = datetime.date.today()

        self.stdout.write(self.style.SUCCESS(f"Collecting metrics from {date_metrics}"))

        users_created = User.objects.filter(date_joined__date=date_metrics).count()
        self.stdout.write(self.style.SUCCESS(f"Users created: {users_created}"))

        active_users = User.objects.filter(last_login__date=date_metrics).count()
        self.stdout.write(self.style.SUCCESS(f"Active users: {active_users}"))

        projects_created = Dashboard.objects.filter(created__date=date_metrics).count()
        self.stdout.write(self.style.SUCCESS(f"Projects created: {projects_created}"))

        completed_tasks = CompletedTask.objects.filter(completed__date=date_metrics).count()
        self.stdout.write(self.style.SUCCESS(f"Completed tasks: {completed_tasks}"))

        if options['save']:
            models.DailyCreatedUsers.objects.update_or_create(date=date_metrics,
                                                              defaults={'total': users_created})
            models.DailyLoggedUsers.objects.update_or_create(date=date_metrics,
                                                             defaults={'total': active_users})
            models.DailyCreatedProjects.objects.update_or_create(date=date_metrics,
                                                                 defaults={'total': projects_created})
            models.DailyCompletedTasks.objects.update_or_create(date=date_metrics,
                                                                defaults={'total': completed_tasks})
            self.stdout.write(self.style.SUCCESS("Results stored in the database"))
