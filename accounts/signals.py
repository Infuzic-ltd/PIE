import logging
from django.conf import settings
from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver

from .models import Lead

logger = logging.getLogger(__name__)

try:
    from .utils.whatsapp import send_whatsapp, send_whatsapp_template
except Exception:
    send_whatsapp = None
    send_whatsapp_template = None


@receiver(pre_save, sender=Lead)
def lead_pre_save(sender, instance, **kwargs):
    # store previous assigned_to id so post_save can detect changes
    if instance.pk:
        try:
            old = Lead.objects.get(pk=instance.pk)
            instance._old_assigned_to_id = old.assigned_to_id
        except Lead.DoesNotExist:
            instance._old_assigned_to_id = None
    else:
        instance._old_assigned_to_id = None


@receiver(post_save, sender=Lead)
def lead_post_save(sender, instance, created, **kwargs):
    old = getattr(instance, '_old_assigned_to_id', None)
    new = instance.assigned_to_id
    # If assignment changed and there is a new assignee, notify them
    if new and old != new:
        agent = instance.assigned_to
        if not agent:
            return
        phone = getattr(agent, 'phone', None)
        if not phone:
            logger.info('Assigned agent %s has no phone number, skipping WhatsApp', agent)
            return

        # Normalize phone: strip spaces and leading '+'
        to_number = phone.strip().lstrip('+').replace(' ', '')

        site = getattr(settings, 'SITE_URL', 'http://localhost:8000').rstrip('/')
        lead_url = f"{site}/crm/leads/{instance.pk}/"
        template_name = getattr(settings, 'WHATSAPP_LEAD_ASSIGNED_TEMPLATE', None)

        try:
            if template_name and send_whatsapp_template:
                # Business-initiated message — must go through an approved template.
                # Template body placeholders: {{1}} agent name, {{2}} lead name, {{3}} lead phone, {{4}} CRM link.
                send_whatsapp_template(
                    to_number,
                    template_name,
                    components=[{
                        'type': 'body',
                        'parameters': [
                            {'type': 'text', 'text': agent.get_full_name() or agent.email},
                            {'type': 'text', 'text': instance.full_name},
                            {'type': 'text', 'text': instance.phone},
                            {'type': 'text', 'text': lead_url},
                        ],
                    }],
                )
            elif send_whatsapp:
                # No approved template configured yet — plain text only reaches the
                # agent if they've messaged the business number within the last 24h.
                message = (
                    f"A lead has been assigned to you:\n"
                    f"Name: {instance.full_name}\n"
                    f"Phone: {instance.phone}\n"
                    f"View: {lead_url}"
                )
                send_whatsapp(to_number, message)
            else:
                logger.warning('WhatsApp send function not available; ensure dependencies are installed')
                return
            logger.info('Sent WhatsApp assignment notification to %s for lead %s', agent.email, instance.pk)
        except Exception:
            logger.exception('Failed sending WhatsApp to %s for lead %s', agent.email, instance.pk)
