"""
URL configuration for insurance_survey project.
"""

from django.contrib import admin
from django.urls import path, include
from django.views.generic import TemplateView, RedirectView
from django.conf import settings
from django.conf.urls.static import static
from django.http import HttpResponse, JsonResponse
from documents.views import secure_media_view
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView


def service_worker_view(request):
    """Serve service worker from root scope with correct headers."""
    sw_path = settings.BASE_DIR / 'static' / 'js' / 'service-worker.js'
    with open(sw_path, 'r') as f:
        response = HttpResponse(f.read(), content_type='application/javascript')
    response['Service-Worker-Allowed'] = '/'
    response['Cache-Control'] = 'no-cache'
    return response


def custom_permission_denied_view(request, exception=None):
    if request.content_type == 'application/json' or 'application/json' in request.headers.get('Accept', ''):
        msg = str(exception) if exception else "Permission denied"
        return JsonResponse({'detail': msg, 'code': 'forbidden'}, status=403)
    from django.views.defaults import permission_denied
    return permission_denied(request, exception)


def custom_bad_request_view(request, exception=None):
    if request.content_type == 'application/json' or 'application/json' in request.headers.get('Accept', ''):
        msg = str(exception) if exception else "Bad request"
        return JsonResponse({'detail': msg, 'code': 'bad_request'}, status=400)
    from django.views.defaults import bad_request
    return bad_request(request, exception)


handler403 = custom_permission_denied_view
handler400 = custom_bad_request_view


urlpatterns = [
    # Admin interface
    path('admin/', admin.site.urls),

    # Root URL redirects to /login/
    path('', RedirectView.as_view(url='/login/', permanent=False), name='home'),

    # PWA: Service worker served from root for full scope control
    path('service-worker.js', service_worker_view, name='service-worker'),

    # PWA offline fallback page
    path('offline/', TemplateView.as_view(template_name='offline.html'), name='offline'),

    # PWA client-side sync issues page
    path('sync-issues/', TemplateView.as_view(template_name='sync_issues.html'), name='sync-issues'),

    # Secure Media File Serving (Authenticated & Claim-permission checked)
    path('media/<path:path>', secure_media_view, name='secure_media'),

    # Admin Web Portal (HTML Views)
    path('', include('claims.web_urls')),
    path('', include('billing.urls')),

    # Authentication Endpoints
    path('api/auth/', include('accounts.urls')),

    # App API Routers (one router per app under /api/)
    path('api/', include('claims.urls')),
    path('api/', include('surveys.urls')),
    path('api/', include('documents.urls')),
    path('api/', include('assessments.urls')),
    path('api/', include('reports.urls')),
    path('api/billing/', include('billing.api_urls')),

    # API Documentation via drf-spectacular
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
]

# Development-mode static file serving (media files served strictly through secure_media_view)
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATICFILES_DIRS[0])
