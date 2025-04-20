from django.urls import path
from .views import LocationCreateView, DriverLocationListView

urlpatterns = [
    path('location/',          LocationCreateView.as_view(),      name='location-create'),
    path('drivers/locations/', DriverLocationListView.as_view(), name='drivers-location-list'),
]
