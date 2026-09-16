from .models import Notification

def global_context(request):
    """
    Supplies global context for navbar, branding, and unread notification alerts.
    """
    context = {
        'BRAND_NAME': 'Future Minds Online',
        'ACADEMY_NAME': 'Future Minds Academy',
        'unread_notifications_count': 0,
        'recent_notifications': [],
    }
    
    if request.user.is_authenticated:
        unread_qs = Notification.objects.filter(recipient=request.user, is_read=False)
        context['unread_notifications_count'] = unread_qs.count()
        context['recent_notifications'] = Notification.objects.filter(recipient=request.user)[:5]
        
    return context
