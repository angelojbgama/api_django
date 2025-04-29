from django.urls import path

from .views import (
    AceitarCorridaView,
    AtualizarAssentosEcoTaxiView,
    AtualizarCorEcoTaxiView,
    AtualizarNomeDispositivoView,
    AtualizarStatusCorridaView,
    AtualizarTipoDispositivoView,
    CorridaAtivaPassageiroView,
    CorridaAtivaEcoTaxiView,
    CorridaDetailView,
    CorridasDoPassageiroView,
    CorridasEcoTaxiHistoricoView,
    CorridasParaEcoTaxiView,
    CorridasDisponiveisParaEcoTaxiView,
    CorridasPorUUIDView,
    CorridasView,
    CriarCorridaView,
    DeletarDispositivoPorUUIDView,
    DispositivoCreateView,
    DispositivoRetrieveUpdateView,
)

urlpatterns = [
    path("corrida/nova/", CriarCorridaView.as_view(), name="nova_corrida"),
    path("corrida/<int:pk>/", CorridaDetailView.as_view(), name="detalhe_corrida"),
    path("corrida/<uuid:uuid>/status/", AtualizarStatusCorridaView.as_view(), name="atualizar_status_corrida"),
    path("corrida/passageiro/<int:passageiro_id>/ativa/", CorridaAtivaPassageiroView.as_view(), name="corrida_ativa"),
    path("corrida/passageiro/<int:passageiro_id>/", CorridasDoPassageiroView.as_view(), name="corridas_passageiro"),

    path("corrida/ecotaxi/<int:pk>/pendentes/", CorridasParaEcoTaxiView.as_view(), name="corridas_para_ecotaxi"),
    path("corrida/ecotaxi/<int:pk>/historico/", CorridasEcoTaxiHistoricoView.as_view(), name="historico_ecotaxi"),

    path("dispositivo/", DispositivoCreateView.as_view(), name="criar_dispositivo"),
    path("dispositivo/<uuid:uuid>/", DispositivoRetrieveUpdateView.as_view(), name="dispositivo_detail"),
    path("dispositivo/<uuid:uuid>/atualizar_nome/", AtualizarNomeDispositivoView.as_view(), name="atualizar_nome_dispositivo"),
    path("dispositivo/<uuid:uuid>/atualizar_tipo/", AtualizarTipoDispositivoView.as_view(), name="atualizar_tipo_dispositivo"),
    path("dispositivo/<uuid:uuid>/deletar/", DeletarDispositivoPorUUIDView.as_view(), name="deletar_dispositivo"),
    path("dispositivo/<uuid:uuid>/atualizar_cor_ecotaxi/", AtualizarCorEcoTaxiView.as_view(), name="atualizar_cor_ecotaxi"),
    path("dispositivo/<uuid:uuid>/atualizar_assentos_ecotaxi/", AtualizarAssentosEcoTaxiView.as_view(), name="atualizar_assentos_ecotaxi"),

    path("corrida/disponiveis/ecotaxi/<uuid:uuid>/", CorridasDisponiveisParaEcoTaxiView.as_view(), name="corridas_disponiveis_ecotaxi"),
    path("corrida/<int:pk>/accept/", AceitarCorridaView.as_view(), name="aceitar_corrida"),
    path("corrida/ativa/ecotaxi/<uuid:uuid>/", CorridaAtivaEcoTaxiView.as_view(), name="corrida_ativa_ecotaxi"),
    path('corridas/<uuid:uuid>/', CorridasView.as_view(), name='corridas'),
    
    path("corrida/uuid/<uuid:uuid>/", CorridasPorUUIDView.as_view(), name="corridas_por_uuid"),
]
