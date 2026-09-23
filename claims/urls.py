from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ClaimViewSet, InsurerViewSet, InsuredViewSet, PolicyViewSet

router = DefaultRouter()
router.register(r'insurers', InsurerViewSet, basename='insurer')
router.register(r'insured', InsuredViewSet, basename='insured')
router.register(r'policies', PolicyViewSet, basename='policy')
router.register(r'claims', ClaimViewSet, basename='claim')

urlpatterns = [
    path('', include(router.urls)),
]
