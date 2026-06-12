from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from master.views import PlantViewSet, ProductViewSet
from challans.views import ChallanViewSet
from rest_framework.authtoken import views as auth_views

router = DefaultRouter()
router.register(r'plants', PlantViewSet)
router.register(r'products', ProductViewSet)
router.register(r'challans', ChallanViewSet)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include(router.urls)),
    path('api/auth/login', auth_views.obtain_auth_token), # Standard DRF Token Login
]