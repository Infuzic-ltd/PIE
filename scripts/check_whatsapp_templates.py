"""Send every PIE WhatsApp template to a test number and check each one arrives.

Uses InstantConvo's two-step flow (see PIE-Template-API.html):
  1. POST /contacts                          save the template values on the contact
  2. POST /contacts/{id}/send/{flow_id}      send the template (a few seconds later)

Step 2 returns {"success": true} as soon as the message is handed to WhatsApp, not when
it is delivered, so after each send the script asks you to confirm it arrived on the phone.

Usage (from the project root):
  python scripts/check_whatsapp_templates.py                    # all templates, confirm each
  python scripts/check_whatsapp_templates.py property_new_listing lead_reminder_alert
  python scripts/check_whatsapp_templates.py --no-confirm       # just send, no prompts
  python scripts/check_whatsapp_templates.py --list

Token: --token, else WHATSAPP_API_TOKEN from the environment or .env.
"""
import argparse
import os
import sys
import time
from pathlib import Path

import requests

BASE_URL = 'https://chat.theinstantconvo.com/api'
DEFAULT_PHONE = '+923122211828'
STEP_GAP = 2.5        # seconds between step 1 and step 2 (values must be saved first)
TEMPLATE_GAP = 5      # seconds between templates, so one send can't pick up the next one's values

# name: (flow_id, contact first_name, {field_name: sample value})
TEMPLATES = {
    'property_new_listing': ('1788774002369', 'Bilal', {
        'tpl_property_ref': 'PROP-0031',
        'tpl_property_summary': 'FL8 — PKR 1.20 Cr',
        'tpl_listed_by': 'Bilal Shaikh',
        'tpl_event_time': '8 Oct 2026, 11:30 AM',
        'tpl_property_id_path': '31/',
    }),
    'property_price_change': ('1788774099337', 'Bilal', {
        'tpl_property_ref': 'PROP-0031',
        'tpl_old_price': 'PKR 1.20 Cr',
        'tpl_new_price': 'PKR 1.15 Cr',
        'tpl_event_time': '8 Oct 2026, 11:40 AM',
        'tpl_property_id_path': '31/',
    }),
    'property_status_change': ('1788774568355', 'Bilal', {
        'tpl_property_ref': 'PROP-0031',
        'tpl_old_status': 'Active',
        'tpl_new_status': 'Sold',
        'tpl_event_time': '8 Oct 2026, 11:45 AM',
        'tpl_property_id_path': '31/',
    }),
    'property_listing_modified': ('1788773236345', 'Bilal', {
        'tpl_property_ref': 'PROP-0031',
        'tpl_changed_field': 'Bedrooms',
        'tpl_old_value': '3',
        'tpl_new_value': '4',
        'tpl_event_time': '8 Oct 2026, 11:50 AM',
        'tpl_property_id_path': '31/',
    }),
    'lead_reminder_alert': ('1788772738324', 'Bilal', {
        'tpl_reminder_category': 'Follow-Up',
        'tpl_first_name': 'Bilal',
        'tpl_reminder_subject': 'Follow-up call with lead Ali Raza',
        'tpl_reminder_datetime': '8 Oct 2026, 4:00 PM',
        'tpl_contact_info': 'Ali Raza (0321-9876543)',
        'tpl_button_path': 'crm/leads/1/',      # button base is the domain root
    }),
    'fyi_internal_alert': ('1788772496335', 'Bilal', {
        'tpl_event_label': 'New Lead Assigned',
        'tpl_first_name': 'Bilal',
        'tpl_event_details': 'Ali Raza (0321-9876543) has been assigned to you. Source: Website Inquiry.',
        'tpl_event_time': '8 Oct 2026, 12:05 PM',
        'tpl_button_path': 'leads/1/',          # button base is /crm/
    }),
    'internal_figures_alert': ('1788772264317', 'Bilal', {
        'tpl_event_label': 'Payment Received',
        'tpl_first_name': 'Bilal',
        'tpl_lead_property_ref': 'Ali Raza - PROP-0031',
        'tpl_figures': 'Paid PKR 500,000 | Balance PKR 750,000',
        'tpl_event_time': '8 Oct 2026, 12:10 PM',
        'tpl_button_path': 'leads/1/',
    }),
    'property_recommendation': ('1788774297339', 'Bilal', {
        'tpl_first_name': 'Bilal',
        'tpl_property_title': 'FL8',
        'tpl_property_location': 'Naya Nazimabad, Karachi',
        'tpl_property_price': 'PKR 1.20 Cr',
        'tpl_property_size_details': '120 Sq Yd, 3 Bed, 3 Bath',
        'tpl_agent_name_phone': 'Bilal Shaikh +923122211828',
        'tpl_property_id_path': '31/',
    }),
    'client_milestone_alert': ('1788772111813', 'Bilal', {
        'tpl_first_name': 'Bilal',
        'tpl_milestone_text': 'Your booking for FL8 has been confirmed.',
        'tpl_agent_name_phone': 'Bilal Shaikh +923122211828',
    }),
    'affiliate_approved_alert': ('1788771644124', 'Bilal', {
        'tpl_first_name': 'Bilal',
    }),
}


def load_token(cli_token):
    if cli_token:
        return cli_token
    if not os.environ.get('WHATSAPP_API_TOKEN'):
        try:
            from dotenv import load_dotenv
            load_dotenv(Path(__file__).resolve().parent.parent / '.env')
        except ImportError:
            pass
    return os.environ.get('WHATSAPP_API_TOKEN', '')


def send(name, phone, headers):
    """Run both steps for one template. Returns (ok, detail)."""
    flow_id, first_name, fields = TEMPLATES[name]
    body = {
        'phone': phone,
        'first_name': first_name,
        'actions': [{'action': 'set_field_value', 'field_name': k, 'value': v} for k, v in fields.items()],
    }
    try:
        r1 = requests.post(f'{BASE_URL}/contacts', json=body, headers=headers, timeout=20)
    except requests.RequestException as e:
        return False, f'step 1 network error: {e}'
    print(f'  step 1 → {r1.status_code} {r1.text[:300]}')
    if r1.status_code == 401:
        return None, 'token rejected (401)'
    try:
        contact_id = r1.json()['data']['id']
    except (ValueError, KeyError, TypeError):
        return False, f'step 1 returned no data.id (HTTP {r1.status_code})'

    time.sleep(STEP_GAP)
    try:
        r2 = requests.post(f'{BASE_URL}/contacts/{contact_id}/send/{flow_id}', headers=headers, timeout=20)
    except requests.RequestException as e:
        return False, f'step 2 network error: {e}'
    print(f'  step 2 → {r2.status_code} {r2.text[:300]}')
    try:
        handed_over = r2.ok and r2.json().get('success') is True
    except ValueError:
        handed_over = False
    return handed_over, 'handed to WhatsApp' if handed_over else f'step 2 failed (HTTP {r2.status_code})'


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('templates', nargs='*', help='template names to send (default: all)')
    p.add_argument('--phone', default=DEFAULT_PHONE, help=f'recipient, +92 format (default {DEFAULT_PHONE})')
    p.add_argument('--token', help='InstantConvo X-ACCESS-TOKEN (default: WHATSAPP_API_TOKEN)')
    p.add_argument('--no-confirm', action='store_true', help="don't ask whether each message arrived")
    p.add_argument('--list', action='store_true', help='list template names and exit')
    args = p.parse_args()

    if args.list:
        print('\n'.join(TEMPLATES))
        return 0
    unknown = [t for t in args.templates if t not in TEMPLATES]
    if unknown:
        sys.exit(f'Unknown template(s): {", ".join(unknown)}. Use --list to see names.')
    token = load_token(args.token)
    if not token:
        sys.exit('No token. Pass --token or set WHATSAPP_API_TOKEN (environment or .env).')

    names = args.templates or list(TEMPLATES)
    headers = {'X-ACCESS-TOKEN': token}
    results = []
    print(f'Sending {len(names)} template(s) to {args.phone}\n')
    for i, name in enumerate(names):
        if i:
            time.sleep(TEMPLATE_GAP)
        print(f'[{i + 1}/{len(names)}] {name}')
        ok, detail = send(name, args.phone, headers)
        if ok is None:  # bad token: every other send would fail the same way
            results.append((name, 'FAIL', detail))
            print(f'  ✗ {detail}. Stopping: get a current token from InstantConvo.\n')
            break
        if ok and not args.no_confirm:
            answer = input('  Did it arrive on the phone with the right text and button? [y/n] ').strip().lower()
            ok = answer.startswith('y')
            detail = 'arrived' if ok else 'handed to WhatsApp but did not arrive correctly'
        results.append((name, 'PASS' if ok else 'FAIL', detail))
        print(f'  {"✓" if ok else "✗"} {detail}\n')

    width = max(len(n) for n, _, _ in results)
    print('Summary')
    for name, status, detail in results:
        print(f'  {status}  {name.ljust(width)}  {detail}')
    passed = sum(s == 'PASS' for _, s, _ in results)
    print(f'\n{passed}/{len(names)} passed')
    return 0 if passed == len(names) else 1


if __name__ == '__main__':
    sys.exit(main())
