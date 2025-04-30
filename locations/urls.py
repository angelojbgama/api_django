from django.urls import path
from .views import (
    # Corrida
    AtualizarDispositivoView,
    CriarCorridaView,
    CorridaDetailView,
    AtualizarStatusCorridaView,
    AceitarCorridaView,
    CorridasView,
    CorridasPorUUIDView,
    # Dispositivo
    DispositivoCreateView,
    DispositivoRetrieveUpdateView,
    AtualizarTipoDispositivoView,
    DeletarDispositivoPorUUIDView,
)

urlpatterns = [
    # Corridas
    path("corrida/nova/", CriarCorridaView.as_view()),
    path("corrida/<int:pk>/", CorridaDetailView.as_view()),
    path("corrida/<uuid:uuid>/status/", AtualizarStatusCorridaView.as_view()),
    path("corrida/<int:pk>/accept/", AceitarCorridaView.as_view()),
    path("corridas/<uuid:uuid>/", CorridasView.as_view()),
    path("corrida/uuid/<uuid:uuid>/", CorridasPorUUIDView.as_view()),
    # Dispositivo
    path("dispositivo/", DispositivoCreateView.as_view()),
    path("dispositivo/<uuid:uuid>/", DispositivoRetrieveUpdateView.as_view()),
    path("dispositivo/<uuid:uuid>/atualizar_tipo/",AtualizarTipoDispositivoView.as_view(),),
    path("dispositivo/<uuid:uuid>/deletar/", DeletarDispositivoPorUUIDView.as_view()),
    path("dispositivo/<uuid:uuid>/atualizar/",AtualizarDispositivoView.as_view(),name="dispositivo_atualizar",),
]
