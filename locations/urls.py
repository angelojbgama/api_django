# locations/urls.py

from django.urls import path
from .views import (
    LocationCreateView,
    DriverLocationListView,
    RideRequestCreateView,
    RideStatusView,
    RideRouteView,
    RidePendingView,   # ← importando a view de pendentes
    RideRespondView,   # ← importando a view de resposta
)

urlpatterns = [
    # 1) atualizações de localização
    path('location/',          LocationCreateView.as_view(),      name='location-create'),

    # 2) última localização de cada EcoTaxi
    path('drivers/locations/', DriverLocationListView.as_view(), name='drivers-location-list'),

    # 3) criar solicitação de corrida
    path('ride/request/',      RideRequestCreateView.as_view(),   name='ride-request'),

    # 4) checar status da corrida
    path('ride/status/',       RideStatusView.as_view(),          name='ride-status'),

    # 5) obter rota (histórico de posições)
    path('ride/route/',        RideRouteView.as_view(),           name='ride-route'),

    # 6) listar solicitações pendentes de um motorista
    path('ride/pending/',      RidePendingView.as_view(),         name='ride-pending'),

    # 7) motorista responde (aceitar/recusar)
    path('ride/respond/',      RideRespondView.as_view(),         name='ride-respond'),
]
