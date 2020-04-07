from django.core.management.base import BaseCommand
from CauldronApp.models import Repository, Dashboard, CompletedTask
from django.db.models import Count, Q

class Command(BaseCommand):
    help = 'Indicates how many repositories and dashboards are affected by the bug of the completed tasks with the field old to False'

    def add_arguments(self, parser):
        parser.add_argument(
            '-f',
            '--fix',
            action='store_true',
            help='Solve inconsistencies'
        )

        parser.add_argument(
            '-l',
            '--list',
            action='store_true',
            help='List the identifiers of the affected resources'
        )

    def handle(self, *args, **options):
        repositories = Repository.objects.annotate(task_count=Count("completedtask", filter=Q(completedtask__old=False)))
        repositories = repositories.filter(task_count__gt=1)

        dashboards = Dashboard.objects.filter(repository__in=repositories).distinct()

        self.stdout.write(self.style.NOTICE(f'Number of repositories affected: {repositories.count()}'))
        self.stdout.write(self.style.NOTICE(f'Number of dashboards affected: {dashboards.count()}'))

        if options['list']:
            self.stdout.write(f'The affected repositories are the following: {[obj.pk for obj in repositories]}')
            self.stdout.write(f'The affected dashboards are the following: {[obj.pk for obj in dashboards]}')

        if options['fix']:
            self.stdout.write(self.style.WARNING('Proceeding to resolve inconsistencies...'))
            tasks_ids = list()

            for repository in repositories:
                tasks = CompletedTask.objects.filter(repository__pk=repository.pk).order_by('-completed')[1:]
                tasks_ids += list(tasks.values_list('pk', flat=True))

            fixed = CompletedTask.objects.filter(pk__in=list(tasks_ids)).update(old=True)
            self.stdout.write(self.style.SUCCESS(f'Number of tasks fixed: {fixed}'))
