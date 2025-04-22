from django.urls import path
from .views import (
    AtualizarTipoDispositivoView,
    CriarCorridaView,
    CorridaDetailView,
    AtualizarStatusCorridaView,
    CorridasDoPassageiroView,
    CorridasParaEcoTaxiView,
    CorridasEcoTaxiHistoricoView,
    CorridaAtivaPassageiroView,
    DispositivoCreateView,
    AtualizarNomeDispositivoView,
    DispositivoDetailView,
    TipoDispositivoView,
    DeletarDispositivoPorUUIDView
)

urlpatterns = [
    # Corridas
    path('corrida/nova/', CriarCorridaView.as_view(), name='nova_corrida'),
    path('corrida/<int:pk>/', CorridaDetailView.as_view(), name='detalhe_corrida'),
    path('corrida/<int:pk>/status/', AtualizarStatusCorridaView.as_view(), name='atualizar_status_corrida'),
    path('corrida/ativa/<int:passageiro_id>/', CorridaAtivaPassageiroView.as_view(), name='corrida_ativa'),
    path('corrida/passageiro/<int:passageiro_id>/', CorridasDoPassageiroView.as_view(), name='corridas_passageiro'),
    path('corrida/ecotaxi/<int:pk>/pendentes/', CorridasParaEcoTaxiView.as_view(), name='corridas_para_ecotaxi'),
    path('corrida/ecotaxi/<int:pk>/historico/', CorridasEcoTaxiHistoricoView.as_view(), name='historico_ecotaxi'),

    # Dispositivo
    path('dispositivo/', DispositivoCreateView.as_view(), name='criar_dispositivo'),
    path('dispositivo/<int:pk>/', DispositivoDetailView.as_view(), name='detalhar_dispositivo'),
    path('dispositivo/<int:pk>/atualizar_nome/', AtualizarNomeDispositivoView.as_view(), name='atualizar_nome_dispositivo'),
    path('dispositivo/<uuid:uuid>/tipo/', TipoDispositivoView.as_view(), name='tipo_dispositivo'),
    path('dispositivo/<uuid:uuid>/deletar/', DeletarDispositivoPorUUIDView.as_view(), name='deletar_dispositivo'),
    path('dispositivo/<int:pk>/atualizar_tipo/', AtualizarTipoDispositivoView.as_view(), name='atualizar_tipo_dispositivo'),

]
