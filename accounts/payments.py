"""Safepay (getsafepay.com) payment gateway integration.

Used for the one-time "Feature My Listing" fee on public property submissions.

IMPORTANT — verify before going live:
Safepay's public API reference (apidocs.getsafepay.com) is a JS-rendered site that
couldn't be scraped for exact current field names. The request/response shape below
is assembled from Safepay's own blog posts, GitHub gists, and support docs available
at the time this was written, and is marked by at least one Safepay engineer as
possibly outdated. Once real sandbox credentials are added in CRM Settings, do a live
test submission and compare the actual response against SAFEPAY_INIT_PATH below —
if Safepay has changed their endpoint shape, this is the only file that needs updating.
"""
import hashlib
import hmac

import requests

SANDBOX_API_BASE = 'https://sandbox.api.getsafepay.com'
PRODUCTION_API_BASE = 'https://api.getsafepay.com'
SANDBOX_CHECKOUT_BASE = 'https://sandbox.api.getsafepay.com/components'
PRODUCTION_CHECKOUT_BASE = 'https://www.getsafepay.com/components'

SAFEPAY_INIT_PATH = '/order/v1/init'


class SafepayError(Exception):
    pass


class SafepayGateway:
    def __init__(self, settings):
        self.settings = settings
        self.is_sandbox = settings.safepay_environment != settings.ENV_PRODUCTION

    @property
    def is_configured(self):
        return self.settings.payments_configured

    def _api_base(self):
        return SANDBOX_API_BASE if self.is_sandbox else PRODUCTION_API_BASE

    def _checkout_base(self):
        return SANDBOX_CHECKOUT_BASE if self.is_sandbox else PRODUCTION_CHECKOUT_BASE

    def create_checkout_session(self, amount, order_id, redirect_url, cancel_url, currency='PKR'):
        """Create a Safepay tracker and return the hosted checkout URL to redirect to."""
        if not self.is_configured:
            raise SafepayError('Safepay is not configured yet — add API keys in CRM Settings.')

        try:
            resp = requests.post(
                f'{self._api_base()}{SAFEPAY_INIT_PATH}',
                json={
                    'client': self.settings.safepay_secret_key,
                    'amount': float(amount),
                    'currency': currency,
                    'environment': self.settings.safepay_environment,
                },
                headers={'Content-Type': 'application/json'},
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as exc:
            raise SafepayError(f'Could not reach Safepay: {exc}') from exc

        token = (data.get('data') or {}).get('token')
        if not token:
            raise SafepayError(f'Unexpected Safepay response: {data}')

        checkout_url = (
            f'{self._checkout_base()}?beacon={token}&source=hosted_checkout'
            f'&order_id={order_id}&redirect_url={redirect_url}&cancel_url={cancel_url}'
        )
        return token, checkout_url

    def verify_webhook_signature(self, payload_body, signature):
        """Best-effort HMAC-SHA256 verification against the secret key.
        Falls back to False (unverified) if we can't confirm — callers should treat an
        unverified webhook as informational only and require manual/admin confirmation."""
        if not signature or not self.settings.safepay_secret_key:
            return False
        expected = hmac.new(
            self.settings.safepay_secret_key.encode(), payload_body, hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, signature)


def get_gateway():
    from .models import SiteSettings
    return SafepayGateway(SiteSettings.load())
