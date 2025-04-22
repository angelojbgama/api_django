from django.urls import path
from .views import (
    AtualizarNomeDispositivoView,
    CorridaAtivaPassageiroView,
    CorridasDoPassageiroView,
    CorridasEcoTaxiHistoricoView,
    CorridasParaEcoTaxiView,
    CriarCorridaView,
    CorridaDetailView,
    AtualizarStatusCorridaView,
    EcoTaxiCreateView,
    EcoTaxiUpdateView,
    PassageiroCreateView,
    PassageiroDetailView
)

urlpatterns = [
    path('corrida/nova/', CriarCorridaView.as_view(), name='nova_corrida'),
    path('corrida/<int:pk>/', CorridaDetailView.as_view(), name='detalhe_corrida'),
    path('corrida/<int:pk>/status/', AtualizarStatusCorridaView.as_view(), name='atualizar_status_corrida'),
    path('passageiro/', PassageiroCreateView.as_view(), name='criar_passageiro'),
    path('ecotaxi/<int:pk>/corridas/', CorridasParaEcoTaxiView.as_view(), name='corridas_para_ecotaxi'),
    path('ecotaxi/', EcoTaxiCreateView.as_view(), name='criar_ecotaxi'),
    path("ecotaxi/<int:pk>/", EcoTaxiUpdateView.as_view(), name="atualizar_ecotaxi"),
    path('ecotaxi/<int:pk>/historico/', CorridasEcoTaxiHistoricoView.as_view(), name='historico_ecotaxi'),
    path('corrida/ativa/<int:passageiro_id>/', CorridaAtivaPassageiroView.as_view(), name='corrida_ativa'),
    path('passageiro/<int:passageiro_id>/corridas/', CorridasDoPassageiroView.as_view(), name='corridas_passageiro'),
    path('dispositivo/<int:pk>/atualizar_nome/', AtualizarNomeDispositivoView.as_view(), name='atualizar_nome_dispositivo'),
    path('passageiro/<int:pk>/', PassageiroDetailView.as_view()),  # para GET do nome atual

]
