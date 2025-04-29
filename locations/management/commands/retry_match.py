from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction
from locations.models import SolicitacaoCorrida, Dispositivo
from locations.utils.ecotaxi_matching import escolher_ecotaxi

class Command(BaseCommand):
    help = 'Re­tenta atribuir ecotaxi às corridas pendentes dos últimos 10 minutos'

    def handle(self, *args, **options):
        agora = timezone.now()
        limite = agora - timedelta(minutes=10)
        pendentes = SolicitacaoCorrida.objects.filter(
            status='pending',
            criada_em__gte=limite
        )
        for corrida in pendentes:
            # se já tiver ecotaxi ainda válido, pula
            if corrida.eco_taxi and agora < corrida.expiracao:
                continue

            et = escolher_ecotaxi(
                corrida.latitude_partida,
                corrida.longitude_partida,
                corrida.assentos_necessarios
            )
            if not et:
                continue

            with transaction.atomic():
                driver = Dispositivo.objects.select_for_update().get(pk=et.pk)
                if driver.assentos_disponiveis < corrida.assentos_necessarios:
                    continue

                driver.assentos_disponiveis -= corrida.assentos_necessarios
                driver.status = 'aguardando'
                driver.save(update_fields=['assentos_disponiveis','status'])

                corrida.eco_taxi = driver
                corrida.expiracao = agora + timedelta(minutes=5)
                corrida.save(update_fields=['eco_taxi','expiracao'])
