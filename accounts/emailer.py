"""Outbound email via the SMTP settings configured on the CRM Settings page.

No credentials are read from environment variables or settings.py — everything
comes from the SiteSettings singleton so admins can set it up without a redeploy.
"""
import smtplib
import socket

from django.core.mail import EmailMultiAlternatives, get_connection
from django.utils.html import strip_tags


class EmailNotConfigured(Exception):
    pass


class EmailSendError(Exception):
    pass


def send_html_email(to_email, subject, html_body):
    from .models import SiteSettings
    settings_obj = SiteSettings.load()
    if not settings_obj.email_configured:
        raise EmailNotConfigured('Email is not configured yet — add SMTP details in CRM Settings.')

    connection = get_connection(
        backend='django.core.mail.backends.smtp.EmailBackend',
        host=settings_obj.smtp_host,
        port=settings_obj.smtp_port,
        username=settings_obj.smtp_username,
        password=settings_obj.smtp_password,
        use_tls=settings_obj.smtp_use_tls,
        fail_silently=False,
        timeout=15,
    )
    message = EmailMultiAlternatives(
        subject=subject,
        body=strip_tags(html_body),
        from_email=settings_obj.from_email,
        to=[to_email],
        connection=connection,
    )
    message.attach_alternative(html_body, 'text/html')
    try:
        message.send()
    except (smtplib.SMTPException, socket.error, OSError) as exc:
        raise EmailSendError(str(exc)) from exc
