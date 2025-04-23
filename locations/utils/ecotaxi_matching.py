# locations/utils/ecotaxi_matching.py
# ===============================================================
#  VERSÃO 100 % UUID (Dispositivo usa uuid como PK)
# ---------------------------------------------------------------
# • Remove TODAS as menções a id.
# • Filtros, exclusões e buscas usam uuid.
# ===============================================================
import logging
from datetime import timedelta
from typing import Optional

from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone
from geopy.distance import geodesic

from locations.models import Dispositivo, SolicitacaoCorrida


def escolher_ecotaxi(
    latitude: float,
    longitude: float,
    assentos_necessarios: int = 1,
    excluir_uuid: str | None = None,   # 👈 agora é uuid
) -> Optional[Dispositivo]:
    filtros = Q(
        tipo="ecotaxi",
        status="aguardando",
        assentos_disponiveis__gte=assentos_necessarios,
        latitude__isnull=False,
        longitude__isnull=False,
    )
    if excluir_uuid:
        filtros &= ~Q(uuid=excluir_uuid)       # 👈 usa uuid aqui

    with transaction.atomic():
        candidatos = list(
            Dispositivo.objects
            .select_for_update(skip_locked=True)
            .filter(filtros)
            .values("uuid", "latitude", "longitude", "assentos_disponiveis")  # 👈 uuid
        )

        if not candidatos:
            return None

        candidatos.sort(
            key=lambda c: geodesic(
                (latitude, longitude),
                (c["latitude"], c["longitude"]),
            ).meters
        )
        ecotaxi_uuid = candidatos[0]["uuid"]   # 👈 pega uuid

        ecotaxi = Dispositivo.objects.select_for_update().get(uuid=ecotaxi_uuid)
        ecotaxi.assentos_disponiveis = F("assentos_disponiveis") - assentos_necessarios
        ecotaxi.status = "aguardando_resposta"
        ecotaxi.save(update_fields=["assentos_disponiveis", "status"])

        return ecotaxi


def repassar_para_proximo_ecotaxi(corrida: SolicitacaoCorrida) -> None:
    if corrida.status not in {"pending", "expired"}:
        return

    novo_ecotaxi = escolher_ecotaxi(
        corrida.latitude_destino,
        corrida.longitude_destino,
        corrida.assentos_necessarios,
        excluir_uuid=corrida.eco_taxi_id,      # 👈 já vem uuid
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
        novo_ecotaxi.uuid,
    )
