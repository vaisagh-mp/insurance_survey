from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ILAViewSet, ISRViewSet, FSRViewSet

router = DefaultRouter()
router.register(r'ila', ILAViewSet, basename='ila')
router.register(r'isr', ISRViewSet, basename='isr')
router.register(r'fsr', FSRViewSet, basename='fsr')

urlpatterns = [
    path('', include(router.urls)),
]
