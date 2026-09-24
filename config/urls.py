"""
URL configuration for insurance_survey project.
"""

from django.contrib import admin
from django.urls import path, include
from django.views.generic import TemplateView, RedirectView
from django.conf import settings
from django.conf.urls.static import static
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

from documents.views import secure_media_view

urlpatterns = [
    # Admin interface
    path('admin/', admin.site.urls),

    # Root URL redirects to /login/
    path('', RedirectView.as_view(url='/login/', permanent=False), name='home'),

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

    # API Documentation via drf-spectacular
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
]

# Development-mode static file serving (media files served strictly through secure_media_view)
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATICFILES_DIRS[0])
