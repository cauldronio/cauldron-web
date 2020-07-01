from django.core.management.base import BaseCommand

from elasticsearch_dsl.connections import connections
from elasticsearch.connection import create_ssl_context
import datetime, calendar
import ssl

from CauldronApp.models import User, Dashboard, CompletedTask
from Cauldron2 import settings
from metrics import models, elastic_models


def first_date(date):
    return date.replace(day=1)


def last_date(date):
    last_day = calendar.monthrange(date.year, date.month)[-1]
    return date.replace(day=last_day)


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
            '--save-elastic',
            action='store_true',
            help="store results in Elastic Search"
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

        projects_per_user = Dashboard.objects.filter(created__date__lte=last_date(date_metrics)).exclude(repository=None).count() / User.objects.filter(date_joined__date__lte=last_date(date_metrics)).count()
        self.stdout.write(self.style.SUCCESS(f"Projects per user: {projects_per_user}"))

        activated_users = User.objects.filter(dashboard__in=Dashboard.objects.exclude(repository=None)).exclude(dashboard__created__date__lt=first_date(date_metrics)).distinct().count()
        self.stdout.write(self.style.SUCCESS(f"Activated Users: {activated_users}"))

        real_users = User.objects.exclude(token=None).filter(date_joined__date__lte=last_date(date_metrics)).count()
        self.stdout.write(self.style.SUCCESS(f"Real Users: {real_users}"))

        m2 = User.objects.exclude(token=None).filter(last_login__month=date_metrics.month, last_login__year=date_metrics.year).count()
        self.stdout.write(self.style.SUCCESS(f"M2: {m2}"))

        m3 = User.objects.filter(dashboard__in=Dashboard.objects.filter(modified__month=date_metrics.month, modified__year=date_metrics.year)).distinct().count()
        self.stdout.write(self.style.SUCCESS(f"M3: {m3}"))

        if options['save']:
            models.MonthlyCreatedUsers.objects.update_or_create(date=date_metrics,
                                                                defaults={'total': users_created})
            models.MonthlyLoggedUsers.objects.update_or_create(date=date_metrics,
                                                               defaults={'total': active_users})
            models.MonthlyCreatedProjects.objects.update_or_create(date=date_metrics,
                                                                   defaults={'total': projects_created})
            models.MonthlyCompletedTasks.objects.update_or_create(date=date_metrics,
                                                                  defaults={'total': completed_tasks})
            models.MonthlyProjectsPerUser.objects.update_or_create(date=date_metrics,
                                                                   defaults={'total': projects_per_user})
            models.MonthlyActivatedUsers.objects.update_or_create(date=date_metrics,
                                                                defaults={'total': activated_users})
            models.MonthlyRealUsers.objects.update_or_create(date=date_metrics,
                                                           defaults={'total': real_users})
            models.MonthlyM2.objects.update_or_create(date=date_metrics,
                                                      defaults={'total': m2})
            models.MonthlyM3.objects.update_or_create(date=date_metrics,
                                                      defaults={'total': m3})

            self.stdout.write(self.style.SUCCESS("Results stored in the database"))

        if options['save_elastic']:
            context = create_ssl_context()
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            connections.create_connection(hosts=[settings.ES_IN_HOST],
                                          scheme=settings.ES_IN_PROTO,
                                          port=settings.ES_IN_PORT,
                                          http_auth=("admin", settings.ES_ADMIN_PASSWORD),
                                          ssl_context=context)

            elastic_models.MonthlyMetrics.init()
            elastic_models.MonthlyMetrics(meta={'id': date_metrics},
                                          date=date_metrics,
                                          created_users=users_created,
                                          logged_users=active_users,
                                          created_projects=projects_created,
                                          completed_tasks=completed_tasks,
                                          projects_per_user=projects_per_user,
                                          activated_users=activated_users,
                                          real_users=real_users,
                                          m2=m2,
                                          m3=m3).save()

            self.stdout.write(self.style.SUCCESS("Results stored in ElasticSearch"))
