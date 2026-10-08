import json
from unittest import mock

from django.test import TestCase, override_settings

from .models import Notification, Property, User, WhatsAppFailure, WhatsAppMessage
from .whatsapp import notify_new_listing


def fake_instantconvo(calls, fail_send=False):
    """Stand-in for requests.post: records each call and answers like InstantConvo."""
    def post(url, json=None, data=None, headers=None, timeout=None):
        calls.append((url, json if json is not None else data, headers))
        r = mock.Mock(status_code=200, text='{}')
        if fail_send and '/send/' in url:
            import requests
            r.status_code, r.text = 500, 'boom'
            r.raise_for_status.side_effect = requests.HTTPError('500 boom', response=r)
        if url.endswith('/contacts'):
            r.json.return_value = {'success': True, 'data': {'id': json['phone'].lstrip('+')}}
        else:
            r.json.return_value = {'success': True}
        return r
    return post


@override_settings(WHATSAPP_API_TOKEN='tok', WHATSAPP_WEBHOOK_KEY='hook')
@mock.patch('accounts.whatsapp.time.sleep', lambda s: None)
class WhatsAppNewListingTests(TestCase):
    def setUp(self):
        self.agent = User.objects.create_user(username='a', email='a@x.pk', password='x', phone='0312-2211828', first_name='Ahmed', last_name='Raza')
        User.objects.create_user(username='b', email='b@x.pk', password='x')  # no phone -> skipped
        User.objects.create_user(username='c', email='c@x.pk', password='x', phone='03001234567',
                                 role=User.ROLE_AFFILIATE, affiliate_status=User.AFFILIATE_STATUS_APPROVED)
        self.prop = Property.objects.create(title='3-Bed Apartment, DHA Phase 6', price=12_000_000, area_size=10,
                                            city='Karachi', location='DHA', created_by=self.agent, show_to_affiliates=False)

    def test_three_step_send_and_failure_callback(self):
        calls = []
        with mock.patch('accounts.whatsapp.requests.post', side_effect=fake_instantconvo(calls)):
            notify_new_listing(self.prop)

        msg = WhatsAppMessage.objects.get()  # affiliate excluded: property not shared with affiliates
        (u1, contact, h1), (u2, custom, _), (u3, _, _) = calls
        self.assertEqual(u1, 'https://chat.theinstantconvo.com/api/contacts')
        self.assertEqual(h1, {'X-ACCESS-TOKEN': 'tok'})
        self.assertEqual(contact['phone'], '+923122211828')
        values = {a['field_name']: a['value'] for a in contact['actions']}
        self.assertEqual(values, {
            'tpl_property_ref': self.prop.property_id, 'tpl_property_summary': '3-Bed Apartment, DHA Phase 6 — PKR 1.20 Cr',
            'tpl_listed_by': 'Ahmed Raza', 'tpl_event_time': values['tpl_event_time'], 'tpl_property_id_path': f'{self.prop.pk}/',
        })
        self.assertEqual(u2, 'https://chat.theinstantconvo.com/api/contacts/923122211828/custom_fields/216066')
        self.assertEqual(custom, {'value': str(msg.message_id)})
        self.assertEqual(u3, 'https://chat.theinstantconvo.com/api/contacts/923122211828/send/1788774002369')

        # InstantConvo echoes custom field 216066 under its own key name; key accepted via ?key= too
        payload = json.dumps({'custom_field': str(msg.message_id), 'error': 'undeliverable'})
        self.assertEqual(self.client.post('/api/whatsapp/failed/', payload, content_type='application/json',
                                          HTTP_X_API_KEY='wrong').status_code, 401)
        for _ in range(2):  # repeated callback must not double-notify
            r = self.client.post('/api/whatsapp/failed/?key=hook', payload, content_type='application/json')
            self.assertEqual(r.status_code, 200)
        msg.refresh_from_db()
        self.assertEqual((msg.status, msg.error), (WhatsAppMessage.STATUS_FAILED, 'undeliverable'))
        self.assertEqual(Notification.objects.filter(recipient=self.agent).count(), 1)
        self.assertEqual(WhatsAppFailure.objects.filter(whatsapp_message=msg, source=WhatsAppFailure.SOURCE_CALLBACK).count(), 2)

    def test_send_error_marks_failed_and_notifies(self):
        with mock.patch('accounts.whatsapp.requests.post', side_effect=fake_instantconvo([], fail_send=True)):
            notify_new_listing(self.prop)
        msg = WhatsAppMessage.objects.get()
        self.assertEqual(msg.status, WhatsAppMessage.STATUS_FAILED)
        self.assertEqual(WhatsAppFailure.objects.get().payload, {'status_code': 500, 'body': 'boom'})
        self.assertEqual(Notification.objects.filter(recipient=self.agent).count(), 1)

    def test_price_and_status_edits_send_their_templates(self):
        self.client.force_login(self.agent)
        with mock.patch('accounts.whatsapp.requests.post', side_effect=fake_instantconvo([])):
            self.client.post(f'/crm/properties/{self.prop.pk}/set-status/', {'status': Property.STATUS_SOLD})
        self.assertEqual(list(WhatsAppMessage.objects.values_list('template_name', flat=True)), ['property_status_change'])

    def test_recommendation_button_and_failure_line(self):
        from .models import Lead
        lead = Lead.objects.create(full_name='Sana Malik', phone='03331234567', assigned_to=self.agent, created_by=self.agent)
        self.client.force_login(self.agent)
        with mock.patch('accounts.whatsapp.requests.post', side_effect=fake_instantconvo(calls := [])):
            r = self.client.post(f'/crm/leads/{lead.pk}/whatsapp/recommend/{self.prop.pk}/')
        body = r.json()
        self.assertEqual((body['ok'], body['status']), (True, 'sent'))
        self.assertEqual(calls[0][1]['phone'], '+923331234567')
        status_url = f'/crm/whatsapp/messages/{body["message_id"]}/'
        self.assertEqual(self.client.get(status_url).json()['status'], 'sent')

        self.client.post('/api/whatsapp/failed/', json.dumps({'message_id': body['message_id']}),
                         content_type='application/json', HTTP_X_API_KEY='hook')
        self.assertEqual(self.client.get(status_url).json()['status'], 'failed')
        # client message failed -> the agent who sent it is told
        self.assertTrue(Notification.objects.filter(recipient=self.agent, title__startswith='WhatsApp not delivered').exists())
        page = self.client.get(f'/crm/leads/{lead.pk}/')
        self.assertContains(page, 'Last send not delivered')
        self.assertContains(page, 'id="shareModalSendApi"')

    def test_webhook_errors_return_json(self):
        post = lambda body: self.client.post('/api/whatsapp/failed/', body, content_type='application/json', HTTP_X_API_KEY='hook')
        self.assertEqual(post('[1, 2]').status_code, 400)
        self.assertEqual(post('{"message_id": "not-a-uuid"}').status_code, 400)
        ok_id = '{"message_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7"}'
        self.assertEqual(post(ok_id).status_code, 404)
        self.assertTrue(WhatsAppFailure.objects.filter(whatsapp_message=None, message_id='7c9e6679-7425-40de-944b-e07fc1f90ae7').exists())
        from django.db import ProgrammingError
        with mock.patch('accounts.whatsapp.WhatsAppMessage.objects.select_related', side_effect=ProgrammingError('no table')):
            r = post(ok_id)
        self.assertEqual(r.status_code, 503)
        self.assertIn('error', r.json())


class TeamWebsiteProfileTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username='adm', email='adm@x.pk', password='x', role=User.ROLE_ADMIN, first_name='Sara', last_name='Admin')
        self.agent = User.objects.create_user(username='ag', email='ag@x.pk', password='x', first_name='Ahmed', last_name='Raza')

    def test_slug_from_name_unique_and_follows_rename(self):
        twin = User.objects.create_user(username='ag2', email='ag2@x.pk', password='x', first_name='Ahmed', last_name='Raza')
        self.assertEqual((self.agent.slug, twin.slug), ('ahmed-raza', 'ahmed-raza-2'))
        self.agent.last_name = 'Khan'
        self.agent.save()
        self.assertEqual(self.agent.slug, 'ahmed-khan')
        twin.save()  # unchanged name keeps its slug
        self.assertEqual(twin.slug, 'ahmed-raza-2')

    def test_publish_toggle_controls_homepage_and_profile(self):
        url = '/team/ahmed-raza/'
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertNotContains(self.client.get('/'), url)

        self.client.force_login(self.admin)
        self.client.post(f'/crm/team/{self.agent.pk}/toggle-website/')
        self.agent.refresh_from_db()
        self.assertTrue(self.agent.show_on_website)

        self.assertContains(self.client.get('/'), url)
        r = self.client.get(url)
        self.assertContains(r, 'Ahmed Raza')

        self.client.post(f'/crm/team/{self.agent.pk}/toggle-website/')
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_toggle_is_admin_only(self):
        self.client.force_login(self.agent)
        self.client.post(f'/crm/team/{self.agent.pk}/toggle-website/')
        self.agent.refresh_from_db()
        self.assertFalse(self.agent.show_on_website)


@override_settings(LEAD_API_KEY='lk')
class LeadApiAgentPhoneTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(username='m', email='m@x.pk', password='x', role=User.ROLE_MANAGER, phone='+92 3008929319')
        self.agent = User.objects.create_user(username='a', email='a@x.pk', password='x', role=User.ROLE_AGENT, phone='')

    def post(self, agent_phone):
        return self.client.post('/api/leads/create/', json.dumps({'full_name': 'Ali', 'phone': '03211234567', 'agent_phone': agent_phone}),
                                content_type='application/json', HTTP_X_API_KEY='lk')

    def test_any_format_matches_manager(self):
        for fmt in ('0300 8929319', '+92 300 8929319', '0092-300-8929319', '3008929319'):
            r = self.post(fmt)
            self.assertEqual(r.status_code, 201, fmt)
            self.assertEqual(r.json()['assigned_agent']['assignment'], 'explicit', fmt)
            self.assertNotIn('warning', r.json())

    def test_unknown_number_still_creates_lead_and_auto_assigns(self):
        for fmt in ('0316 5939101', '12'):
            r = self.post(fmt)
            self.assertEqual(r.status_code, 201, fmt)
            body = r.json()
            self.assertEqual(body['assigned_agent']['assignment'], 'auto')
            self.assertEqual(body['assigned_agent']['name'], self.agent.get_full_name())
            self.assertIn('warning', body)


@override_settings(LEAD_API_KEY='lk')
class LeadApiNeverLosesLeadTests(TestCase):
    def setUp(self):
        self.agent = User.objects.create_user(username='a', email='a@x.pk', password='x', role=User.ROLE_AGENT)

    def send(self, body, content_type='application/json'):
        r = self.client.post('/api/leads/create/', body, content_type=content_type, HTTP_X_API_KEY='lk')
        self.assertEqual(r.status_code, 201, r.content)
        from .models import Lead
        return r.json(), Lead.objects.get(pk=r.json()['id'])

    def test_unknown_source_becomes_chatbot(self):
        body, lead = self.send(json.dumps({'full_name': 'Ali', 'phone': '0321', 'source': 'chat bot widget', 'lead_type': 'buyerr'}))
        self.assertEqual((lead.source, lead.lead_type, lead.assigned_to), ('chatbot', 'buyer', self.agent))
        self.assertIn('chatbot', body['warning'])

    def test_missing_name_and_phone_still_saved(self):
        body, lead = self.send(json.dumps({'email': 'x@y.pk'}))
        self.assertEqual((lead.full_name, lead.phone, lead.email), ('Unknown', '', 'x@y.pk'))

    def test_invalid_json_kept_in_notes(self):
        body, lead = self.send('name=Ali; phone=0300 {broken', content_type='application/json')
        self.assertIn('phone=0300', lead.notes)

    def test_json_without_json_content_type(self):
        body, lead = self.send(json.dumps({'full_name': 'Sana', 'phone': '0333'}), content_type='text/plain')
        self.assertEqual((lead.full_name, lead.phone), ('Sana', '0333'))

    def test_out_of_range_budget_ignored(self):
        body, lead = self.send(json.dumps({'full_name': 'Big', 'phone': '0300', 'budget_min': '1' + '0' * 30, 'budget_max': 'NaN'}))
        self.assertEqual((lead.budget_min, lead.budget_max), (None, None))

    def test_failed_save_falls_back_to_minimal_lead(self):
        from .models import Lead
        real_save, calls = Lead.save, []
        def flaky_save(obj, *a, **kw):
            calls.append(1)
            if len(calls) == 1:
                raise ValueError('db rejected a field')
            return real_save(obj, *a, **kw)
        with mock.patch.object(Lead, 'save', flaky_save):
            body, lead = self.send(json.dumps({'full_name': 'Ali', 'phone': '0300', 'area_preferences': 'DHA'}))
        self.assertEqual((lead.full_name, lead.phone), ('Ali', '0300'))
        self.assertIn('area_preferences', lead.notes)
        self.assertIn('original payload', body['warning'])

    def test_notification_failure_does_not_lose_lead(self):
        with mock.patch('accounts.views.notify_user', side_effect=RuntimeError('push down')):
            body, lead = self.send(json.dumps({'full_name': 'Ali', 'phone': '0300'}))
        self.assertEqual(lead.full_name, 'Ali')

    def test_wrong_key_still_refused(self):
        r = self.client.post('/api/leads/create/', '{}', content_type='application/json', HTTP_X_API_KEY='nope')
        self.assertEqual(r.status_code, 401)


class WhatsAppRecommendFiveTests(TestCase):
    @override_settings(WHATSAPP_API_TOKEN='tok')
    @mock.patch('accounts.whatsapp.time.sleep', lambda s: None)
    def test_five_properties_sent_as_five_messages(self):
        from .models import Lead
        agent = User.objects.create_user(username='a', email='a@x.pk', password='x', phone='03122211828', first_name='Ahmed')
        lead = Lead.objects.create(full_name='Sana Malik', phone='03331234567', assigned_to=agent, created_by=agent)
        props = [Property.objects.create(title=f'House {i}', price=10_000_000 + i, area_size=5, city='Karachi',
                                         location='Naya Nazimabad', created_by=agent) for i in range(5)]
        self.client.force_login(agent)
        calls = []
        with mock.patch('accounts.whatsapp.requests.post', side_effect=fake_instantconvo(calls)):
            for p in props:  # the dialog sends them one request at a time
                self.assertEqual(self.client.post(f'/crm/leads/{lead.pk}/whatsapp/recommend/{p.pk}/').json()['status'], 'sent')
        msgs = WhatsAppMessage.objects.filter(lead=lead, template_name='property_recommendation')
        self.assertEqual(sorted(msgs.values_list('property_id', flat=True)), sorted(p.pk for p in props))
        paths = [{a['field_name']: a['value'] for a in body['actions']}['tpl_property_id_path']
                 for url, body, _ in calls if url.endswith('/contacts')]
        self.assertEqual(paths, [f'{p.pk}/' for p in props])
        self.assertEqual(len([u for u, _, _ in calls if '/send/1788774297339' in u]), 5)


@override_settings(WHATSAPP_API_TOKEN='tok')
@mock.patch('accounts.whatsapp.time.sleep', lambda s: None)
class WhatsAppLeadTriggerTests(TestCase):
    def test_milestone_to_client_and_deal_lost_to_agent_and_admins(self):
        from .models import Lead
        from .whatsapp import on_lead_status_changed
        agent = User.objects.create_user(username='a', email='a@x.pk', password='x', phone='03122211828')
        admin = User.objects.create_user(username='ad', email='ad@x.pk', password='x', phone='03001112223', role=User.ROLE_ADMIN)
        lead = Lead.objects.create(full_name='Sana Malik', phone='03331234567', assigned_to=agent, status=Lead.STATUS_BOOKING_CONFIRMED)
        calls = []
        with mock.patch('accounts.whatsapp.requests.post', side_effect=fake_instantconvo(calls)):
            on_lead_status_changed(lead, Lead.STATUS_NEGOTIATION)
            lead.status, lead.lost_reason = Lead.STATUS_DEAL_LOST, 'Budget'
            on_lead_status_changed(lead, Lead.STATUS_BOOKING_CONFIRMED)
        sent = sorted(WhatsAppMessage.objects.values_list('template_name', 'phone'))
        self.assertEqual(sent, [('client_milestone_alert', '923331234567'),
                                ('fyi_internal_alert', '923001112223'), ('fyi_internal_alert', '923122211828')])
        milestone = {a['field_name']: a['value'] for a in calls[0][1]['actions']}
        self.assertEqual(milestone['tpl_milestone_text'], 'Your booking for your property has been confirmed.')
