import os
from django.core.management.base import BaseCommand
from core.models import User


class Command(BaseCommand):
    help = 'Creates or updates a production administrator/superuser from environment variables.'

    def handle(self, *args, **options):
        username = os.environ.get('DJANGO_SUPERUSER_USERNAME', os.environ.get('ADMIN_USERNAME'))
        password = os.environ.get('DJANGO_SUPERUSER_PASSWORD', os.environ.get('ADMIN_PASSWORD'))
        email = os.environ.get('DJANGO_SUPERUSER_EMAIL', os.environ.get('ADMIN_EMAIL', 'admin@futureminds.academy'))
        first_name = os.environ.get('ADMIN_FIRST_NAME', 'Academy')
        last_name = os.environ.get('ADMIN_LAST_NAME', 'Director')

        if not username or not password:
            self.stdout.write(self.style.WARNING(
                "Skipping auto-admin: DJANGO_SUPERUSER_USERNAME or DJANGO_SUPERUSER_PASSWORD is not set."
            ))
            return

        user, created = User.objects.get_or_create(
            username=username,
            defaults={
                'email': email,
                'first_name': first_name,
                'last_name': last_name,
                'role': User.Role.ADMIN,
                'is_staff': True,
                'is_superuser': True,
                'phone': '+20 100 000 0001'
            }
        )

        user.role = User.Role.ADMIN
        user.is_staff = True
        user.is_superuser = True
        user.email = email
        user.set_password(password)
        user.save()

        if created:
            self.stdout.write(self.style.SUCCESS(f"Successfully created production admin '{username}'."))
        else:
            self.stdout.write(self.style.SUCCESS(f"Successfully updated production admin '{username}'."))
