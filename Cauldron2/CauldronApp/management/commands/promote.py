from django.core.management.base import BaseCommand
from django.core.exceptions import MultipleObjectsReturned
from django.contrib.auth.models import User

class Command(BaseCommand):
    help = 'Promotes users to superusers'

    def add_arguments(self, parser):
        parser.add_argument('usernames', nargs='+', type=str)

        parser.add_argument(
            '-d',
            '--delete',
            action='store_true',
            help='Degrades a superuser to user '
        )

    def handle(self, *args, **options):
        for username in options['usernames']:
            try:
                user = User.objects.get(first_name=username)
            except User.DoesNotExist:
                self.stderr.write(self.style.ERROR('User "%s" does not exist' % username))
                continue
            except MultipleObjectsReturned:
                self.stderr.write(self.style.ERROR('There are more than one user with username "%s"' % username))
                continue

            if options['delete']:
                user.is_staff = False
                user.is_superuser = False
            else:
                user.is_staff = True
                user.is_superuser = True

            user.save()
            self.stdout.write(self.style.SUCCESS('Successfully modified user "%s"' % username))
