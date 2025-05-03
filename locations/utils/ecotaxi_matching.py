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
    excluir_uuid: str | None = None,
    debitar_assentos: bool = True,  # 👈 novo parâmetro
) -> Optional[Dispositivo]:
    filtros = Q(
        tipo="ecotaxi",
        status="aguardando",
        assentos_disponiveis__gte=assentos_necessarios,
        latitude__isnull=False,
        longitude__isnull=False,
    )

    if excluir_uuid:
        filtros &= ~Q(uuid=excluir_uuid)

    with transaction.atomic():
        candidatos = list(
            Dispositivo.objects
            .select_for_update(skip_locked=True)
            .filter(filtros)
            .values("uuid", "latitude", "longitude", "assentos_disponiveis")
        )

        if not candidatos:
            return None

        candidatos.sort(
            key=lambda c: geodesic(
                (latitude, longitude),
                (c["latitude"], c["longitude"]),
            ).meters
        )

        ecotaxi_uuid = candidatos[0]["uuid"]
        ecotaxi = Dispositivo.objects.select_for_update().get(uuid=ecotaxi_uuid)

        if debitar_assentos:
            ecotaxi.assentos_disponiveis = F("assentos_disponiveis") - assentos_necessarios
            ecotaxi.status = "aguardando_resposta"
            ecotaxi.save(update_fields=["assentos_disponiveis", "status"])
        else:
            ecotaxi.status = "aguardando"
            ecotaxi.save(update_fields=["status"])

        ecotaxi.refresh_from_db()
        return ecotaxi

def repassar_para_proximo_ecotaxi(corrida: SolicitacaoCorrida) -> None:
    if corrida.status != "pending":
        return

    uuid_atual = str(corrida.eco_taxi_id) if corrida.eco_taxi_id else None

    novo_ecotaxi = escolher_ecotaxi(
        latitude=corrida.latitude_destino,
        longitude=corrida.longitude_destino,
        assentos_necessarios=corrida.assentos_necessarios,
        excluir_uuid=uuid_atual,  # ❌ exclui o atual
    )

    # Nenhum novo ecotaxi encontrado
    if not novo_ecotaxi:
        logging.info("🚫 Nenhum novo EcoTaxi disponível para corrida %s", corrida.id)
        return

    # Se retornou o mesmo ecotaxi por algum erro, não faz nada
    if novo_ecotaxi.uuid == corrida.eco_taxi_id:
        logging.warning("⚠️ EcoTaxi novo é o mesmo da corrida %s — ignorando", corrida.id)
        return

    corrida.eco_taxi  = novo_ecotaxi
    corrida.expiracao = timezone.now() + timedelta(minutes=5)
    corrida.save(update_fields=["eco_taxi", "expiracao"])
    logging.info(
        "🔄 Corrida %s repassada para novo EcoTaxi %s",
        corrida.id,
        novo_ecotaxi.uuid,
    )
