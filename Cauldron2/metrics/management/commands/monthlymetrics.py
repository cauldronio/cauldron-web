from django.core.management.base import BaseCommand
from CauldronApp.models import User, Dashboard, CompletedTask
from metrics import models

import datetime


class Command(BaseCommand):
    help = 'Collect metrics related to Cauldron from the current month.'

    def add_arguments(self, parser):
        parser.add_argument(
            '-s',
            '--save',
            action='store_true',
            help="store results in database"
        )

        parser.add_argument(
            '--date',
            type=lambda s: datetime.datetime.strptime(s, '%Y-%m').date(),
            help="metrics from a specific month (YYYY-MM)"
        )

        parser.add_argument(
            '--previous-month',
            action='store_true',
            help="metrics from previous month"
        )

    def handle(self, *args, **options):
        if options['date'] and options['previous_month']:
            self.stderr.write(self.style.ERROR("Cannot use '--date' and '--previous-month' at the same time"))
            return

        if options['previous_month']:
            date_metrics = datetime.date.today().replace(day=1) - datetime.timedelta(days=1)
        elif options['date']:
            date_metrics = options['date']
        else:
            date_metrics = datetime.date.today()

        self.stdout.write(self.style.SUCCESS(f"Collecting metrics from {date_metrics.strftime('%Y-%m')}"))

        users_created = User.objects.filter(date_joined__month=date_metrics.month,
                                            date_joined__year=date_metrics.year).count()
        self.stdout.write(self.style.SUCCESS(f"Users created: {users_created}"))

        active_users = User.objects.filter(last_login__month=date_metrics.month,
                                           last_login__year=date_metrics.year).count()
        self.stdout.write(self.style.SUCCESS(f"Active users: {active_users}"))

        projects_created = Dashboard.objects.filter(created__month=date_metrics.month,
                                                    created__year=date_metrics.year).count()
        self.stdout.write(self.style.SUCCESS(f"Projects created: {projects_created}"))

        completed_tasks = CompletedTask.objects.filter(completed__month=date_metrics.month,
                                                       completed__year=date_metrics.year).count()
        self.stdout.write(self.style.SUCCESS(f"Completed tasks: {completed_tasks}"))

        if options['save']:
            models.MonthlyCreatedUsers.objects.update_or_create(date=date_metrics,
                                                                defaults={'total': users_created})
            models.MonthlyLoggedUsers.objects.update_or_create(date=date_metrics,
                                                               defaults={'total': active_users})
            models.MonthlyCreatedProjects.objects.update_or_create(date=date_metrics,
                                                                   defaults={'total': projects_created})
            models.MonthlyCompletedTasks.objects.update_or_create(date=date_metrics,
                                                                  defaults={'total': completed_tasks})

            self.stdout.write(self.style.SUCCESS("Results stored in the database"))
