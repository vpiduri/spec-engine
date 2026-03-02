from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'accounts', views.AccountViewSet, basename='account')

urlpatterns = [
    path('', include(router.urls)),
    path('accounts/<str:account_id>/', views.AccountDetailView.as_view()),
]
