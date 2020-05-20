from django.core.management.base import BaseCommand

from elasticsearch_dsl.connections import connections
from elasticsearch.connection import create_ssl_context
import datetime
import ssl

from Cauldron2 import settings
from CauldronApp.models import User, Dashboard, CompletedTask
from metrics import models, elastic_models


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
            '--save-elastic',
            action='store_true',
            help="store results in Elastic Search"
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

        if options['save_elastic']:
            context = create_ssl_context()
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            connections.create_connection(hosts=[settings.ES_IN_HOST],
                                          scheme=settings.ES_IN_PROTO,
                                          port=settings.ES_IN_PORT,
                                          http_auth=("admin", settings.ES_ADMIN_PASSWORD),
                                          ssl_context=context)

            elastic_models.DailyMetrics.init()
            elastic_models.DailyMetrics(meta={'id': date_metrics},
                                        date=date_metrics,
                                        created_users=users_created,
                                        logged_users=active_users,
                                        created_projects=projects_created,
                                        completed_tasks=completed_tasks).save()

            self.stdout.write(self.style.SUCCESS("Results stored in ElasticSearch"))
