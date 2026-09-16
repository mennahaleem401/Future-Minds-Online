from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from django.shortcuts import redirect
from django.views.static import serve

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', lambda request: redirect('dashboard_redirect'), name='home'),
    path('', include('core.urls')),
    path('', include('academy.urls')),
    path('', include('assessment.urls')),
]

# Ensure media files (avatars, lesson booklets, assignment uploads) are accessible in both development and production
urlpatterns += [
    re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATICFILES_DIRS[0])
