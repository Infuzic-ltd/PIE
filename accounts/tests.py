import json
from unittest import mock

from django.test import TestCase, override_settings

from .models import Notification, Property, User, WhatsAppFailure, WhatsAppMessage
from .whatsapp import notify_new_listing


@override_settings(WHATSAPP_API_TOKEN='tok', WHATSAPP_WEBHOOK_KEY='hook')
class WhatsAppNewListingTests(TestCase):
    def test_send_and_failure_callback(self):
        agent = User.objects.create_user(username='a', email='a@x.pk', password='x', phone='0312-2211828', first_name='Ahmed', last_name='Raza')
        User.objects.create_user(username='b', email='b@x.pk', password='x')  # no phone -> skipped
        User.objects.create_user(username='c', email='c@x.pk', password='x', phone='03001234567',
                                 role=User.ROLE_AFFILIATE, affiliate_status=User.AFFILIATE_STATUS_APPROVED)
        prop = Property.objects.create(title='3-Bed Apartment, DHA Phase 6', price=12_000_000, area_size=10,
                                       city='Karachi', location='DHA', created_by=agent, show_to_affiliates=False)

        with mock.patch('accounts.whatsapp.requests.post') as post:
            notify_new_listing(prop)

        msg = WhatsAppMessage.objects.get()  # affiliate excluded: property not shared with affiliates
        url, kwargs = post.call_args.args[0], post.call_args.kwargs
        body = kwargs['json']
        self.assertEqual(url, 'https://chat.theinstantconvo.com/api/contacts/923122211828/send/text')
        self.assertEqual(kwargs['headers'], {'X-ACCESS-TOKEN': 'tok'})
        self.assertEqual(body['contact_id'], '923122211828')
        self.assertEqual(body['message_id'], str(msg.message_id))
        comps = body['message']['components']
        self.assertEqual(comps[0]['parameters'][0]['text'], prop.property_id)
        self.assertEqual(comps[1]['parameters'][0]['text'], '3-Bed Apartment, DHA Phase 6 — PKR 1.20 Cr')
        self.assertEqual(comps[1]['parameters'][1]['text'], 'Ahmed Raza')
        self.assertEqual(comps[2]['parameters'][0]['text'], f'{prop.pk}/')

        payload = json.dumps({'message_id': str(msg.message_id), 'error': 'undeliverable'})
        self.assertEqual(self.client.post('/api/whatsapp/failed/', payload, content_type='application/json',
                                          HTTP_X_API_KEY='wrong').status_code, 401)
        for _ in range(2):  # repeated callback must not double-notify
            r = self.client.post('/api/whatsapp/failed/', payload, content_type='application/json', HTTP_X_API_KEY='hook')
            self.assertEqual(r.status_code, 200)
        msg.refresh_from_db()
        self.assertEqual((msg.status, msg.error), (WhatsAppMessage.STATUS_FAILED, 'undeliverable'))
        self.assertEqual(Notification.objects.filter(recipient=agent).count(), 1)
        # every authenticated callback is logged, including the repeat
        self.assertEqual(WhatsAppFailure.objects.filter(whatsapp_message=msg, source=WhatsAppFailure.SOURCE_CALLBACK).count(), 2)

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
