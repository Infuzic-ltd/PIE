def notifications(request):
    if not request.user.is_authenticated:
        return {}
    qs = request.user.notifications.all()[:8]
    return {
        'nav_notifications': qs,
        'unread_notifications_count': request.user.notifications.filter(is_read=False).count(),
    }
