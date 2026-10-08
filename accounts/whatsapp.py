"""WhatsApp template messages via InstantConvo, and their delivery-failure callback.

Sending one template takes three calls (see PIE-Template-API.html):
  1. POST /contacts                                   save the template values on the contact
  2. POST /contacts/{id}/custom_fields/216066         store our message_id, echoed back on failure
  3. POST /contacts/{id}/send/{flow_id}               send, a couple of seconds after 1-2

Step 3 returns {"success": true} as soon as WhatsApp accepts the message, not when it is
delivered. Real failures arrive later at `whatsapp_failed_webhook` with our message_id, and
`_mark_failed` raises an in-CRM notification instead.

Every public notify_*/send_* function is safe to call from a view: errors are logged, never raised.
"""
import json
import logging
import re
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from zoneinfo import ZoneInfo

import requests
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db import DatabaseError
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .models import Lead, User, WhatsAppFailure, WhatsAppMessage

API = 'https://chat.theinstantconvo.com/api'
MESSAGE_ID_FIELD = '216066'   # InstantConvo custom field returned in their failure callback
STEP_GAP = 2.5                # seconds between saving values and sending (sending too early = 0 params)
COMPANY_PHONE = '+92 311 1222141'
PKT = ZoneInfo('Asia/Karachi')
logger = logging.getLogger(__name__)

FLOWS = {
    'property_new_listing': '1788774002369',
    'property_price_change': '1788774099337',
    'property_status_change': '1788774568355',
    'property_listing_modified': '1788773236345',
    'lead_reminder_alert': '1788772738324',
    'fyi_internal_alert': '1788772496335',
    'internal_figures_alert': '1788772264317',
    'property_recommendation': '1788774297339',
    'client_milestone_alert': '1788772111813',
    'affiliate_approved_alert': '1788771644124',
}

MILESTONE_TEXT = {
    Lead.STATUS_BOOKING_CONFIRMED: 'Your booking for {property} has been confirmed.',
    Lead.STATUS_DOCUMENTATION: 'Your file has moved into documentation. Our team will contact you about next steps.',
    Lead.STATUS_POSSESSION_COMPLETE: 'Possession of your property is now complete. Congratulations!',
    Lead.STATUS_DEAL_CLOSED: 'Your deal has been successfully closed. Thank you for choosing PIE Real Estate!',
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _normalize_phone_digits(raw):
    """Digits only, with a Pakistani local '0...' prefix rewritten to the '92...' country code
    so local and international formats of the same number compare equal."""
    digits = re.sub(r'\D', '', raw or '')
    if digits.startswith('0') and len(digits) == 11:
        digits = '92' + digits[1:]
    return digits


def _clean(value):
    """WhatsApp rejects empty values and values with line breaks, tabs or 4+ spaces."""
    return re.sub(r'\s+', ' ', str(value or '')).strip()[:250] or '-'


def _when(dt=None):
    dt = timezone.localtime(dt or timezone.now(), PKT)
    return f'{dt.day} {dt:%b %Y}, {dt.hour % 12 or 12}:{dt:%M %p}'


def _first_name(user_or_lead):
    name = getattr(user_or_lead, 'first_name', '') or getattr(user_or_lead, 'full_name', '') or ''
    return name.split()[0] if name.split() else 'there'


def _name_phone(user):
    if not user:
        return f'PIE Real Estate ({COMPANY_PHONE})'
    return f'{user.get_full_name()} ({user.phone})' if user.phone else user.get_full_name()


def _unique(users):
    seen, out = set(), []
    for u in users:
        if u and u.pk not in seen and u.is_active and u.phone:
            seen.add(u.pk)
            out.append(u)
    return out


def _item(template, phone, first_name, fields, **row):
    """One message to send. `row` holds WhatsAppMessage fields (recipient, lead, property, sent_by, notify_*)."""
    return {'template': template, 'phone': phone, 'first_name': first_name, 'fields': fields, 'row': row}


# ── Sending ───────────────────────────────────────────────────────────────────

def _send(items):
    """Send a batch and return the WhatsAppMessage rows. Never raises."""
    try:
        return _send_batch(items)
    except Exception:
        logger.exception('WhatsApp batch send failed')
        return []


def _send_batch(items):
    if not settings.WHATSAPP_API_TOKEN:
        return []
    pairs = []
    for it in items:
        digits = _normalize_phone_digits(it['phone'])
        if len(digits) < 10:
            continue
        msg = WhatsAppMessage.objects.create(phone=digits, template_name=it['template'], **it['row'])
        pairs.append((msg, it))
    # Template values live on the contact, so the same number twice in one batch would overwrite
    # its own values: send repeats in later rounds.
    rounds = []
    for pair in pairs:
        for r in rounds:
            if all(m.phone != pair[0].phone for m, _ in r):
                r.append(pair)
                break
        else:
            rounds.append([pair])
    for r in rounds:
        _send_round(r)
    return [m for m, _ in pairs]


def _attempt(fn, arg):
    try:
        return fn(arg), None
    except Exception as e:  # network, HTTP status, unexpected JSON
        return None, e


def _send_round(pairs):
    # ponytail: values are stored per contact, so two requests messaging the same person at the same
    # moment can still mix values; a per-contact queue would fix it if that ever shows up.
    headers = {'X-ACCESS-TOKEN': settings.WHATSAPP_API_TOKEN}

    def checked(r):
        # InstantConvo reports some errors as HTTP 200 with {"error": {...}} in the body.
        r.raise_for_status()
        body = r.json()
        if 'error' in body:
            raise ValueError(f'InstantConvo error: {r.text[:300]}')
        return body

    def prepare(pair):
        msg, it = pair
        body = {
            'phone': '+' + msg.phone,
            'first_name': _clean(it['first_name']),
            'actions': [{'action': 'set_field_value', 'field_name': k, 'value': _clean(v)} for k, v in it['fields'].items()],
        }
        contact_id = checked(requests.post(f'{API}/contacts', json=body, headers=headers, timeout=10))['data']['id']
        # Form-encoded on purpose: this endpoint rejects a JSON body.
        checked(requests.post(f'{API}/contacts/{contact_id}/custom_fields/{MESSAGE_ID_FIELD}',
                              data={'value': str(msg.message_id)}, headers=headers, timeout=10))
        return contact_id

    def send(pair_and_contact):
        (msg, it), contact_id = pair_and_contact
        body = checked(requests.post(f'{API}/contacts/{contact_id}/send/{FLOWS[it["template"]]}', headers=headers, timeout=10))
        if body.get('success') is not True:
            raise ValueError(f'InstantConvo did not accept the message: {body}')

    errors = []
    with ThreadPoolExecutor(max_workers=8) as pool:  # HTTP only in threads; DB writes below, in this thread
        prepared = list(pool.map(lambda p: _attempt(prepare, p), pairs))
        ready = []
        for pair, (contact_id, err) in zip(pairs, prepared):
            if err:
                errors.append((pair[0], err))
            else:
                ready.append((pair, contact_id))
        if ready:
            time.sleep(STEP_GAP)
            for (pair, _), (_, err) in zip(ready, pool.map(lambda pc: _attempt(send, pc), ready)):
                if err:
                    errors.append((pair[0], err))
    for msg, err in errors:
        resp = getattr(err, 'response', None)
        WhatsAppFailure.objects.create(
            whatsapp_message=msg, message_id=msg.message_id, source=WhatsAppFailure.SOURCE_SEND, error=str(err)[:1000],
            payload={'status_code': resp.status_code, 'body': resp.text[:2000]} if resp is not None else {},
        )
        _mark_failed(msg, err)


def _mark_failed(msg, error):
    """Record the failure and raise an in-CRM notification (bell + web push).
    Staff alert → the staff member who missed it. Client message → whoever sent it, else the lead's agent."""
    msg.status = WhatsAppMessage.STATUS_FAILED
    msg.error = str(error or '')[:1000]
    msg.save(update_fields=['status', 'error'])
    if not msg.notify_title:
        return  # this event already raised its own in-app notification
    target = msg.recipient or msg.sent_by or (msg.lead.assigned_to if msg.lead_id else None)
    if target:
        from .views import notify_user  # views imports this module
        notify_user(target, msg.notify_title, msg.notify_body, msg.notify_url)


# ── Property alerts (staff + affiliates) ──────────────────────────────────────

def _property_audience(prop):
    audience = ~Q(role=User.ROLE_AFFILIATE)
    if prop.show_to_affiliates:
        audience |= Q(role=User.ROLE_AFFILIATE, affiliate_status=User.AFFILIATE_STATUS_APPROVED)
    return User.objects.filter(audience, is_active=True).exclude(phone='')


def _property_alert(prop, template, fields, title, body):
    fields = {'tpl_property_ref': prop.property_id, **fields,
              'tpl_event_time': _when(), 'tpl_property_id_path': f'{prop.pk}/'}
    url = reverse('property_view', args=[prop.pk])
    return _send([
        _item(template, u.phone, u.first_name or u.get_full_name(), fields,
              recipient=u, property=prop, notify_title=title, notify_body=body, notify_url=url)
        for u in _property_audience(prop)
    ])


def listing_summary(prop):
    return f'{prop.title} — {prop.price_display()}'


def notify_new_listing(prop):
    summary = listing_summary(prop)
    creator = prop.created_by.get_full_name() if prop.created_by else 'PIE CRM'
    return _property_alert(prop, 'property_new_listing',
                           {'tpl_property_summary': summary, 'tpl_listed_by': creator},
                           f'New listing: {prop.property_id}', summary)


def notify_price_change(prop, old_price):
    new_price = prop.price_display()
    return _property_alert(prop, 'property_price_change',
                           {'tpl_old_price': old_price, 'tpl_new_price': new_price},
                           f'Price update: {prop.property_id}', f'{prop.title}: {old_price} → {new_price}')


def notify_status_change(prop, old_status):
    new_status = prop.get_status_display()
    return _property_alert(prop, 'property_status_change',
                           {'tpl_old_status': old_status, 'tpl_new_status': new_status},
                           f'Status update: {prop.property_id}', f'{prop.title}: {old_status} → {new_status}')


def notify_listing_modified(prop, changed_field, old_value, new_value):
    return _property_alert(prop, 'property_listing_modified',
                           {'tpl_changed_field': changed_field, 'tpl_old_value': old_value, 'tpl_new_value': new_value},
                           f'Listing updated: {prop.property_id}', f'{prop.title}: {changed_field} changed')


# ── Internal lead alerts ──────────────────────────────────────────────────────

def _fyi(users, label, details, button_path, notify_url, lead=None, fallback=True):
    fields = {'tpl_event_label': label, 'tpl_event_details': details, 'tpl_event_time': _when(),
              'tpl_button_path': button_path}
    return _send([
        _item('fyi_internal_alert', u.phone, _first_name(u), {**fields, 'tpl_first_name': _first_name(u)},
              recipient=u, lead=lead, notify_title=label if fallback else '', notify_body=details, notify_url=notify_url)
        for u in _unique(users)
    ])


def notify_lead_assigned(lead):
    """The assignment already raises an in-app notification, so no extra one on WhatsApp failure."""
    details = f'{lead.full_name} ({lead.phone}) has been assigned to you. Source: {lead.get_source_display()}.'
    return _fyi([lead.assigned_to], 'New Lead Assigned', details, f'leads/{lead.pk}/',
                f'/crm/leads/{lead.pk}/', lead=lead, fallback=False)


def notify_deal_lost(lead):
    agent = lead.assigned_to.get_full_name() if lead.assigned_to else 'Unassigned'
    details = f'Deal lost for lead {lead.full_name}. Reason: {lead.lost_reason or "Not given"}. Agent: {agent}.'
    admins = User.objects.filter(role=User.ROLE_ADMIN)
    return _fyi([lead.assigned_to, *admins], 'Deal Lost', details, f'leads/{lead.pk}/', f'/crm/leads/{lead.pk}/', lead=lead)


def notify_submission_received(submission):
    details = f'Submission {submission.reference_code()} from {submission.full_name} is awaiting evaluation.'
    admins = User.objects.filter(role=User.ROLE_ADMIN)
    return _fyi(admins, 'Submission Received', details, f'property-submissions/{submission.pk}/',
                f'/crm/property-submissions/{submission.pk}/')


def notify_lead_figures(lead, label, figures):
    """internal_figures_alert to the lead's agent and the finance team."""
    ref = f'{lead.full_name} - {lead.property.property_id}' if lead.property_id else lead.full_name
    finance = User.objects.filter(financial_person=True)
    fields = {'tpl_event_label': label, 'tpl_lead_property_ref': ref, 'tpl_figures': figures,
              'tpl_event_time': _when(), 'tpl_button_path': f'leads/{lead.pk}/'}
    return _send([
        _item('internal_figures_alert', u.phone, _first_name(u), {**fields, 'tpl_first_name': _first_name(u)},
              recipient=u, lead=lead, property=lead.property,
              notify_title=label, notify_body=f'{ref}: {figures}', notify_url=f'/crm/leads/{lead.pk}/')
        for u in _unique([lead.assigned_to, *finance])
    ])


# ── Client messages (leads) ───────────────────────────────────────────────────

def _client_item(lead, template, fields, what, prop=None, sent_by=None):
    """A message to the lead; if it fails, the sender (or the lead's agent) is told in the CRM."""
    return _item(template, lead.phone, _first_name(lead), fields, lead=lead, property=prop, sent_by=sent_by,
                 notify_title=f'WhatsApp not delivered to {lead.full_name}',
                 notify_body=f'{what} could not be delivered on WhatsApp. Please contact them directly.',
                 notify_url=f'/crm/leads/{lead.pk}/')


def notify_visit_scheduled(lead, prop, visit_dt):
    """lead_reminder_alert to the client and to the lead's agent and collaborators."""
    when = _when(visit_dt)
    public = prop.show_on_website and prop.status == prop.STATUS_ACTIVE
    items = [_client_item(lead, 'lead_reminder_alert', {
        'tpl_reminder_category': 'Site Visit', 'tpl_first_name': _first_name(lead),
        'tpl_reminder_subject': f'Site visit for {prop.title}', 'tpl_reminder_datetime': when,
        'tpl_contact_info': _name_phone(lead.assigned_to),
        'tpl_button_path': f'properties/{prop.pk}/' if public else 'contact/',
    }, f'The site visit reminder for {prop.title}', prop=prop)] if lead.phone else []
    for u in _unique([lead.assigned_to, *lead.collaborators.all()]):
        items.append(_item('lead_reminder_alert', u.phone, _first_name(u), {
            'tpl_reminder_category': 'Site Visit', 'tpl_first_name': _first_name(u),
            'tpl_reminder_subject': f'Site visit with {lead.full_name} at {prop.title}',
            'tpl_reminder_datetime': when, 'tpl_contact_info': f'{lead.full_name} ({lead.phone})',
            'tpl_button_path': f'crm/leads/{lead.pk}/',
        }, recipient=u, lead=lead, property=prop))  # agents already get an in-app notification
    return _send(items)


def notify_client_milestone(lead):
    text = MILESTONE_TEXT.get(lead.status)
    if not text or not lead.phone:
        return []
    text = text.format(property=lead.property.title if lead.property_id else 'your property')
    return _send([_client_item(lead, 'client_milestone_alert', {
        'tpl_first_name': _first_name(lead), 'tpl_milestone_text': text,
        'tpl_agent_name_phone': _name_phone(lead.assigned_to),
    }, f'The update "{lead.get_status_display()}"', prop=lead.property)])


def on_lead_status_changed(lead, old_status):
    """Call after a lead's status is saved."""
    if lead.status == old_status:
        return
    if lead.status in MILESTONE_TEXT:
        notify_client_milestone(lead)
    elif lead.status == Lead.STATUS_DEAL_LOST:
        notify_deal_lost(lead)


def send_property_recommendation(lead, prop, sent_by):
    """Manual send from the lead page. Returns the WhatsAppMessage, or None if nothing was sent."""
    size = ', '.join(x for x in [
        prop.size_display(),
        f'{prop.bedrooms} Bed' if prop.bedrooms else '',
        f'{prop.bathrooms} Bath' if prop.bathrooms else '',
    ] if x)
    msgs = _send([_client_item(lead, 'property_recommendation', {
        'tpl_first_name': _first_name(lead), 'tpl_property_title': prop.title,
        'tpl_property_location': ', '.join(x for x in [prop.location, prop.city] if x),
        'tpl_property_price': prop.price_display(), 'tpl_property_size_details': size,
        'tpl_agent_name_phone': _name_phone(lead.assigned_to or sent_by),
        'tpl_property_id_path': f'{prop.pk}/',
    }, f'The recommendation for {prop.title}', prop=prop, sent_by=sent_by)])
    return msgs[0] if msgs else None


def notify_affiliate_approved(affiliate):
    """Approval already raises an in-app notification, so no extra one on WhatsApp failure."""
    if not affiliate.phone:
        return []
    return _send([_item('affiliate_approved_alert', affiliate.phone, _first_name(affiliate),
                        {'tpl_first_name': _first_name(affiliate)}, recipient=affiliate)])


# ── Views ─────────────────────────────────────────────────────────────────────

UUID_RE = re.compile(r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}')


def _find_message_id(data):
    """Our UUID from the callback: `message_id` if present, else the first UUID anywhere in the payload
    (InstantConvo sends back the value of custom field 216066, whatever they name it)."""
    if isinstance(data, dict) and data.get('message_id'):
        try:
            return uuid.UUID(str(data['message_id']))
        except ValueError:
            pass
    m = UUID_RE.search(json.dumps(data, default=str))
    return uuid.UUID(m.group(0)) if m else None


def _find_error(data):
    if isinstance(data, dict):
        for key in ('error', 'reason', 'error_message', 'message', 'status'):
            if data.get(key):
                return data[key] if isinstance(data[key], str) else json.dumps(data[key], default=str)
    return ''


@csrf_exempt
@require_POST
def whatsapp_failed_webhook(request):
    """InstantConvo calls this when a message isn't delivered, carrying our message_id."""
    key = request.headers.get('X-Api-Key') or request.GET.get('key')
    if not settings.WHATSAPP_WEBHOOK_KEY or key != settings.WHATSAPP_WEBHOOK_KEY:
        return JsonResponse({'error': 'Invalid or missing API key.'}, status=401)
    try:
        data = json.loads(request.body or b'{}')
    except ValueError:
        data = request.POST.dict()
    message_id = _find_message_id(data)
    if not message_id:
        logger.warning('WhatsApp failure webhook: no message_id in payload %s', str(data)[:2000])
        return JsonResponse({'error': 'Body must contain our message_id (UUID).'}, status=400)

    try:
        msg = WhatsAppMessage.objects.select_related('recipient', 'property', 'lead', 'sent_by').filter(message_id=message_id).first()
        WhatsAppFailure.objects.create(
            whatsapp_message=msg, message_id=message_id, source=WhatsAppFailure.SOURCE_CALLBACK,
            error=str(_find_error(data))[:1000], payload=data if isinstance(data, dict) else {'body': data},
        )
        if not msg:
            return JsonResponse({'error': 'Unknown message_id.'}, status=404)
        if msg.status == WhatsAppMessage.STATUS_FAILED:
            return JsonResponse({'ok': True})  # already handled — callbacks may repeat
        _mark_failed(msg, _find_error(data))
    except DatabaseError:
        logger.exception('WhatsApp failure webhook: database error for message_id %s', message_id)
        return JsonResponse({'error': 'Temporarily unavailable, please retry later.'}, status=503)
    except Exception:
        logger.exception('WhatsApp failure webhook: unexpected error for message_id %s', message_id)
        return JsonResponse({'error': 'Internal server error, please retry later.'}, status=500)
    return JsonResponse({'ok': True})


@login_required
def whatsapp_message_status(request, message_id):
    """Polled by the lead page after a manual send, to show a red line if delivery failed."""
    msg = get_object_or_404(WhatsAppMessage, message_id=message_id)
    if not (request.user.is_crm_admin or msg.sent_by_id == request.user.pk):
        return JsonResponse({'error': 'Not allowed.'}, status=403)
    return JsonResponse({'status': msg.status, 'error': msg.error})


def whatsapp_api_docs(request):
    return render(request, 'website/whatsapp_api_docs.html')
