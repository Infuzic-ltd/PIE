from django.apps import AppConfig


class AccountsConfig(AppConfig):
    name = 'accounts'
    def ready(self):
        # Import signal handlers to wire lead assignment notifications
        try:
            import accounts.signals  # noqa: F401
        except Exception:
            # Avoid raising on import errors during manage.py checks
            pass
