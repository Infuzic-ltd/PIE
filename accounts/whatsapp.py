"""WhatsApp template sends via InstantConvo + their delivery-failure callback.

InstantConvo's send endpoint returns success whether or not the message is
delivered, so each send carries our own `message_id` UUID. When delivery fails
they POST that id to `whatsapp_failed_webhook`, which falls back to an in-CRM
notification for the recipient.
"""
import json
import re
import uuid
from zoneinfo import ZoneInfo

import requests
from django.conf import settings
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .models import User, WhatsAppMessage

SEND_URL = 'https://chat.theinstantconvo.com/api/contacts/{contact_id}/send/text'
PKT = ZoneInfo('Asia/Karachi')


def _normalize_phone_digits(raw):
    """Digits only, with a Pakistani local '0...' prefix rewritten to the '92...' country code
    so local and international formats of the same number compare equal."""
    digits = re.sub(r'\D', '', raw or '')
    if digits.startswith('0') and len(digits) == 11:
        digits = '92' + digits[1:]
    return digits


def send_template(user, template_name, components, prop=None):
    """Send one template message to `user` and log it. Returns the WhatsAppMessage row."""
    contact_id = _normalize_phone_digits(user.phone)
    msg = WhatsAppMessage.objects.create(
        message_id=uuid.uuid4(), recipient=user, phone=contact_id,
        template_name=template_name, property=prop,
    )
    payload = {
        'contact_id': contact_id,
        'message_id': str(msg.message_id),
        'message': {
            'type': 'template',
            'channel': 'omnichannel',
            'template_name': template_name,
            'language': {'code': 'en_US'},
            'components': components,
        },
    }
    try:
        resp = requests.post(
            SEND_URL.format(contact_id=contact_id),
            json=payload,
            headers={'X-ACCESS-TOKEN': settings.WHATSAPP_API_TOKEN},
            timeout=10,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        _mark_failed(msg, e)
    return msg


def _listing_summary(prop):
    return f'{prop.title} — {prop.price_display()}'


def _mark_failed(msg, error):
    """Record the failure and fall back to an in-CRM notification (bell popup + web push) for the recipient."""
    msg.status = WhatsAppMessage.STATUS_FAILED
    msg.error = str(error or '')[:1000]
    msg.save(update_fields=['status', 'error'])
    if msg.property:
        from .views import notify_user  # views imports this module
        notify_user(
            msg.recipient,
            f'New listing: {msg.property.property_id}',
            _listing_summary(msg.property),
            url=reverse('property_view', args=[msg.property.pk]),
        )


def notify_new_listing(prop):
    """WhatsApp `property_new_listing` to all active staff (+ approved affiliates if the property is shared with them)."""
    if not settings.WHATSAPP_API_TOKEN:
        return
    try:
        audience = ~Q(role=User.ROLE_AFFILIATE)
        if prop.show_to_affiliates:
            audience |= Q(role=User.ROLE_AFFILIATE, affiliate_status=User.AFFILIATE_STATUS_APPROVED)
        recipients = User.objects.filter(audience, is_active=True).exclude(phone='')

        creator = prop.created_by.get_full_name() if prop.created_by else 'PIE CRM'
        listed_at = prop.created_at.astimezone(PKT)
        components = [
            {'type': 'header', 'parameters': [{'type': 'text', 'text': prop.property_id}]},
            {'type': 'body', 'parameters': [
                {'type': 'text', 'text': _listing_summary(prop)},
                {'type': 'text', 'text': creator},
                {'type': 'text', 'text': f'{listed_at.day} {listed_at:%b %Y}, {listed_at.hour % 12 or 12}:{listed_at:%M %p}'},
            ]},
            {'type': 'button', 'sub_type': 'url', 'index': '0',
             'parameters': [{'type': 'text', 'text': str(prop.pk)}]},
        ]
        # ponytail: synchronous, one HTTP call per recipient inside the request; move to a queue/cron if listing gets slow.
        for user in recipients:
            send_template(user, 'property_new_listing', components, prop=prop)
    except Exception:
        pass  # a WhatsApp outage must never break property creation


@csrf_exempt
@require_POST
def whatsapp_failed_webhook(request):
    """InstantConvo calls this with {"message_id": "<uuid>", "error": "..."} when a message isn't delivered."""
    if not settings.WHATSAPP_WEBHOOK_KEY or request.headers.get('X-Api-Key') != settings.WHATSAPP_WEBHOOK_KEY:
        return JsonResponse({'error': 'Invalid or missing API key.'}, status=401)
    try:
        data = json.loads(request.body)
        message_id = uuid.UUID(str(data['message_id']))
    except (ValueError, KeyError, TypeError):
        return JsonResponse({'error': 'Body must be JSON with a valid "message_id" UUID.'}, status=400)

    msg = WhatsAppMessage.objects.select_related('recipient', 'property').filter(message_id=message_id).first()
    if not msg:
        return JsonResponse({'error': 'Unknown message_id.'}, status=404)
    if msg.status == WhatsAppMessage.STATUS_FAILED:
        return JsonResponse({'ok': True})  # already handled — callbacks may repeat

    _mark_failed(msg, data.get('error'))
    return JsonResponse({'ok': True})


def whatsapp_api_docs(request):
    return render(request, 'website/whatsapp_api_docs.html', {
        'api_token': settings.WHATSAPP_API_TOKEN or 'not set',
        'webhook_key': settings.WHATSAPP_WEBHOOK_KEY or 'not set',
    })
