from django.urls import path
from .views import (
    CorridasParaEcoTaxiView,
    CriarCorridaView,
    CorridaDetailView,
    AtualizarStatusCorridaView,
    PassageiroCreateView
)

urlpatterns = [
    path('corrida/nova/', CriarCorridaView.as_view(), name='nova_corrida'),
    path('corrida/<int:pk>/', CorridaDetailView.as_view(), name='detalhe_corrida'),
    path('corrida/<int:pk>/status/', AtualizarStatusCorridaView.as_view(), name='atualizar_status_corrida'),
    path('passageiro/', PassageiroCreateView.as_view(), name='criar_passageiro'),
    path('ecotaxi/<int:pk>/corridas/', CorridasParaEcoTaxiView.as_view(), name='corridas_para_ecotaxi'),

]
