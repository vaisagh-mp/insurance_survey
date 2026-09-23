from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ClaimDocumentViewSet, RequirementViewSet

router = DefaultRouter()
router.register(r'documents', ClaimDocumentViewSet, basename='document')
router.register(r'requirements', RequirementViewSet, basename='requirement')

urlpatterns = [
    path('', include(router.urls)),
]
