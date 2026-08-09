import time

from django.core.management.base import BaseCommand, CommandError

from accounts.models import User
from accounts.views import notify_user


class Command(BaseCommand):
    help = (
        "Create a test Notification for a user so you can watch the notification "
        "bell (red dot, sound, ring animation) pick it up on its next poll. "
        "Usage: python3 manage.py send_test_notification you@example.com"
    )

    def add_arguments(self, parser):
        parser.add_argument('email', help="Recipient's login email.")
        parser.add_argument('--title', default='Test Notification', help='Notification title.')
        parser.add_argument('--body', default='This is a test notification sent from the CLI.', help='Notification body text.')
        parser.add_argument('--url', default='/crm/dashboard/', help='Link the notification should open.')
        parser.add_argument('--count', type=int, default=1, help='How many notifications to send.')
        parser.add_argument('--delay', type=float, default=0, help='Seconds to wait between each one (with --count > 1).')

    def handle(self, *args, **options):
        email = options['email']
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            raise CommandError(f'No user found with email "{email}".')

        count = options['count']
        for i in range(count):
            title = options['title'] if count == 1 else f"{options['title']} #{i + 1}"
            notify_user(user, title, options['body'], options['url'])
            self.stdout.write(self.style.SUCCESS(f'Sent "{title}" to {user.email}.'))
            if i < count - 1 and options['delay'] > 0:
                time.sleep(options['delay'])

        self.stdout.write(self.style.SUCCESS(
            f"Done. {user.email} now has "
            f"{user.notifications.filter(is_read=False).count()} unread notification(s)."
        ))
