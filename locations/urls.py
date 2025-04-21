# locations/urls.py

from django.urls import path
from .views import (
    LocationCreateView,
    DriverLocationListView,
    RidePendingView,
    RideRequestCreateView,
    RideRespondView,
    RideStatusView,
    RideRouteView,
)

urlpatterns = [
    # já existente
    path('location/',          LocationCreateView.as_view(),      name='location-create'),
    path('drivers/locations/', DriverLocationListView.as_view(), name='drivers-location-list'),

    # novos endpoints de corrida
    path('ride/request/',      RideRequestCreateView.as_view(),   name='ride-request'),
    path('ride/status/',       RideStatusView.as_view(),          name='ride-status'),
    path('ride/route/',        RideRouteView.as_view(),           name='ride-route'),
    path('ride/pending/',      RidePendingView.as_view(),         name='ride-pending'),
    path('ride/respond/',      RideRespondView.as_view(),         name='ride-respond'),

]
