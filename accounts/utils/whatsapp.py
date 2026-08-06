import logging
from django.conf import settings
import requests

logger = logging.getLogger(__name__)

API_VERSION = getattr(settings, 'WHATSAPP_API_VERSION', 'v17.0')
PHONE_ID = getattr(settings, 'WHATSAPP_PHONE_ID', None)
TOKEN = getattr(settings, 'WHATSAPP_API_TOKEN', None)
GRAPH_API_BASE = f'https://graph.facebook.com/{API_VERSION}'


def send_whatsapp(to_number: str, message_text: str) -> dict:
    """Send a plain-text WhatsApp message using Meta Cloud API.

    to_number should be in international format without the leading '+', e.g. '92300...'
    Returns the parsed JSON response on success, raises on failure.
    """
    if not PHONE_ID or not TOKEN:
        raise RuntimeError('WhatsApp API credentials not configured (WHATSAPP_PHONE_ID/WHATSAPP_API_TOKEN)')

    url = f"{GRAPH_API_BASE}/{PHONE_ID}/messages"
    headers = {
        'Authorization': f'Bearer {TOKEN}',
        'Content-Type': 'application/json',
    }
    payload = {
        'messaging_product': 'whatsapp',
        'to': to_number,
        'type': 'text',
        'text': {'body': message_text},
    }

    resp = requests.post(url, headers=headers, json=payload, timeout=15)
    try:
        resp.raise_for_status()
        return resp.json()
    except Exception:
        logger.exception('Failed to send WhatsApp message to %s: %s %s', to_number, resp.status_code if resp is not None else None, getattr(resp, 'text', None))
        raise


def send_whatsapp_template(to_number: str, template_name: str, language_code: str = 'en_US', components: list | None = None) -> dict:
    """Send a pre-approved WhatsApp template message using Meta Cloud API.

    Required for any business-initiated message (the recipient hasn't messaged
    the business number within the last 24h) — plain text via send_whatsapp()
    is rejected by WhatsApp in that case. `components` follows Meta's template
    components format, e.g.:
    [
        {'type': 'header', 'parameters': [{'type': 'image', 'image': {'link': 'https://...'}}]},
        {'type': 'body', 'parameters': [{'type': 'text', 'text': 'Ali Raza'}, ...]},
    ]
    """
    if not PHONE_ID or not TOKEN:
        raise RuntimeError('WhatsApp API credentials not configured (WHATSAPP_PHONE_ID/WHATSAPP_API_TOKEN)')

    url = f"{GRAPH_API_BASE}/{PHONE_ID}/messages"
    headers = {
        'Authorization': f'Bearer {TOKEN}',
        'Content-Type': 'application/json',
    }
    template = {'name': template_name, 'language': {'code': language_code}}
    if components:
        template['components'] = components
    payload = {
        'messaging_product': 'whatsapp',
        'to': to_number,
        'type': 'template',
        'template': template,
    }

    resp = requests.post(url, headers=headers, json=payload, timeout=15)
    try:
        resp.raise_for_status()
        return resp.json()
    except Exception:
        logger.exception('Failed to send WhatsApp template %s to %s: %s %s', template_name, to_number, resp.status_code if resp is not None else None, getattr(resp, 'text', None))
        raise
