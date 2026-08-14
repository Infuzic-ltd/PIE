def notifications(request):
    if not request.user.is_authenticated:
        return {}
    from .models import PropertySubmission
    qs = request.user.notifications.all()[:8]
    return {
        'nav_notifications': qs,
        'unread_notifications_count': request.user.notifications.filter(is_read=False).count(),
        'pending_submissions_count': PropertySubmission.objects.filter(status=PropertySubmission.STATUS_PENDING).count(),
    }
