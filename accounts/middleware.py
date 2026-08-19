from django.shortcuts import render, redirect
from django.urls import resolve, Resolver404

# Affiliates are external workers invited by an individual agent — not CRM staff — so they
# get a deny-by-default allowlist instead of the normal PERMISSION_DEFAULTS system. This is
# enforced centrally here rather than scattered across every view, so nothing new added to
# the CRM is accidentally exposed to affiliates.

AFFILIATE_PENDING_ALLOWED_URL_NAMES = {
    'affiliate_pending', 'logout',
}

AFFILIATE_APPROVED_ALLOWED_URL_NAMES = {
    'affiliate_home', 'affiliate_pending', 'logout', 'change_password',
    'property_list', 'property_view',
    'lead_list', 'lead_detail', 'lead_update', 'lead_status_update',
    'lead_add_note', 'lead_add_document', 'lead_share_properties',
    'lead_auto_follow_up', 'lead_schedule_visit',
    'notifications_list', 'notification_open', 'notifications_mark_all_read', 'notifications_feed',
    'service_worker', 'push_subscribe', 'push_unsubscribe', 'push_test',
}


class AffiliateAccessMiddleware:
    """Restricts logged-in affiliates to a small allowlist of CRM URLs. A pending
    (not-yet-approved) affiliate can only reach the pending-approval page; an approved
    one can only reach the affiliate-facing pages. Everything else — Dashboard, Team,
    Customers, Roles, Settings, property/lead mutation, financials, etc. — is blocked.
    Only applies under /crm/ so the public marketing site is never affected."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, 'user', None)
        if request.path.startswith('/crm/') and user is not None and user.is_authenticated and user.role == 'affiliate':
            try:
                url_name = resolve(request.path_info).url_name
            except Resolver404:
                url_name = None

            if user.affiliate_status != user.AFFILIATE_STATUS_APPROVED:
                if url_name not in AFFILIATE_PENDING_ALLOWED_URL_NAMES:
                    return redirect('affiliate_pending')
            elif url_name not in AFFILIATE_APPROVED_ALLOWED_URL_NAMES:
                return render(request, 'accounts/403.html', status=403)

        return self.get_response(request)
