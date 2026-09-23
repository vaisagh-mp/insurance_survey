from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import SurveyTypeViewSet, InspectionViewSet

router = DefaultRouter()
router.register(r'survey-types', SurveyTypeViewSet, basename='survey-type')
router.register(r'inspections', InspectionViewSet, basename='inspection')

urlpatterns = [
    path('', include(router.urls)),
]
