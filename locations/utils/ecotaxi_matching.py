# locations/utils/ecotaxi_matching.py
# ================================================================
#  VERSÃO “geopy-only”
#  ---------------------------------------------------------------
#  • Remove TODO código/dep. GIS (Distance, Point, GDAL, PostGIS)
#  • Calcula distância em Python usando geopy.geodesic
#  • Mantém transações e bloqueio pessimista (select_for_update)
# ================================================================
import logging
from datetime import timedelta
from typing import Optional

from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone
from geopy.distance import geodesic          # ← cálculo de distância em Python

from locations.models import Dispositivo, SolicitacaoCorrida


# ------------------------------------------------------------------
# FUNÇÃO PRINCIPAL: escolher o EcoTaxi mais próximo
# ------------------------------------------------------------------
def escolher_ecotaxi(
    latitude: float,
    longitude: float,
    assentos_necessarios: int = 1,
    excluir_id: int | None = None,
) -> Optional[Dispositivo]:
    """
    • Procura EcoTaxis em status 'aguardando', com assentos suficientes.
    • Ordena TODOS pela distância (geopy.geodesic) em memória.
    • Bloqueia a linha do EcoTaxi escolhido (select_for_update) para
      evitar corrida – e já reserva os assentos.
    """
    filtros = Q(
        tipo="ecotaxi",
        status="aguardando",
        assentos_disponiveis__gte=assentos_necessarios,
        latitude__isnull=False,
        longitude__isnull=False,
    )
    if excluir_id:
        filtros &= ~Q(id=excluir_id)

    with transaction.atomic():
        # 🔒 bloqueia *somente* na hora que realmente vamos alterar
        candidatos = list(
            Dispositivo.objects
            .select_for_update(skip_locked=True)
            .filter(filtros)
            .values("id", "latitude", "longitude", "assentos_disponiveis")
        )

        if not candidatos:
            return None

        # ▶️  Ordena em memória pela menor distância
        candidatos.sort(
            key=lambda c: geodesic(
                (latitude, longitude),
                (c["latitude"], c["longitude"]),
            ).meters
        )
        ecotaxi_id = candidatos[0]["id"]

        # 🔄 Busca a instância bloqueada para atualizar
        ecotaxi = Dispositivo.objects.select_for_update().get(id=ecotaxi_id)
        ecotaxi.assentos_disponiveis = F("assentos_disponiveis") - assentos_necessarios
        ecotaxi.status = "aguardando_resposta"
        ecotaxi.save(update_fields=["assentos_disponiveis", "status"])

        return ecotaxi


# ------------------------------------------------------------------
# REPASSE AUTOMÁTICO (expirou ou motorista rejeitou)
# ------------------------------------------------------------------
def repassar_para_proximo_ecotaxi(corrida: SolicitacaoCorrida) -> None:
    """
    • Tenta encontrar um novo motorista.
    • Se não houver → status = expired.
    • Se encontrar   → atribui, reinicia expiração, reserva assentos.
    """
    if corrida.status not in {"pending", "expired"}:
        return  # já aceita ou concluída

    novo_ecotaxi = escolher_ecotaxi(
        corrida.latitude_destino,
        corrida.longitude_destino,
        corrida.assentos_necessarios,
        excluir_id=corrida.eco_taxi_id,
    )

    if not novo_ecotaxi:
        corrida.status = "expired"
        corrida.save(update_fields=["status"])
        logging.info("🚫 Nenhum EcoTaxi disponível — corrida %s expirada.", corrida.id)
        return

    corrida.eco_taxi  = novo_ecotaxi
    corrida.status    = "pending"
    corrida.expiracao = timezone.now() + timedelta(minutes=5)
    corrida.save(update_fields=["eco_taxi", "status", "expiracao"])
    logging.info(
        "🔄 Corrida %s repassada para EcoTaxi %s",
        corrida.id,
        novo_ecotaxi.id,
    )
