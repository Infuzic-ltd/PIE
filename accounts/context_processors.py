def notifications(request):
    if not request.user.is_authenticated:
        return {}
    from .models import PropertySubmission, User
    qs = request.user.notifications.all()[:8]

    if request.user.is_crm_admin:
        pending_affiliates_count = User.objects.filter(
            role=User.ROLE_AFFILIATE, affiliate_status=User.AFFILIATE_STATUS_PENDING,
        ).count()
    elif request.user.role in (User.ROLE_AGENT, User.ROLE_MANAGER):
        pending_affiliates_count = User.objects.filter(
            role=User.ROLE_AFFILIATE, affiliate_status=User.AFFILIATE_STATUS_PENDING, invited_by=request.user,
        ).count()
    else:
        pending_affiliates_count = 0

    return {
        'nav_notifications': qs,
        'unread_notifications_count': request.user.notifications.filter(is_read=False).count(),
        'pending_submissions_count': PropertySubmission.objects.filter(status=PropertySubmission.STATUS_PENDING).count(),
        'pending_affiliates_count': pending_affiliates_count,
    }
