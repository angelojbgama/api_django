import uuid
from datetime import timedelta

from django.db import models
from django.utils import timezone


def default_expiracao() -> timezone.datetime:
    return timezone.now() + timedelta(minutes=5)


class Dispositivo(models.Model):
    TIPO_CHOICES = [
        ("passageiro", "Passageiro"),
        ("ecotaxi",    "EcoTaxi"),
    ]

    STATUS_CHOICES = [
        ("aguardando",           "Aguardando Corrida"),
        ("aguardando_resposta",  "Aguardando Resposta"),
        ("transito",             "Em Trânsito"),
        ("fora",                 "Fora de Serviço"),
    ]

    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nome = models.CharField(max_length=100)
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES)
    cor_ecotaxi = models.CharField(max_length=50, null=True, blank=True)

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="fora",
    )
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    assentos_disponiveis = models.PositiveIntegerField(default=4, null=True, blank=True)

    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"{self.nome} ({self.tipo})"


class SolicitacaoCorrida(models.Model):
    STATUS_CHOICES = [
        ("pending",   "Pendente"),
        ("accepted",  "Aceita"),
        ("started",   "Em Trânsito"),
        ("rejected",  "Recusada"),
        ("cancelled", "Cancelada"),
        ("completed", "Concluída"),
        ("expired",   "Expirada"),
    ]

    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)

    passageiro = models.ForeignKey(
        Dispositivo,
        on_delete=models.CASCADE,
        related_name="corridas_passageiro",
    )
    eco_taxi = models.ForeignKey(
        Dispositivo,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="corridas_ecotaxi",
        limit_choices_to={"tipo": "ecotaxi"},
    )

    latitude_partida  = models.FloatField()
    longitude_partida = models.FloatField()
    endereco_partida  = models.CharField(max_length=255, blank=True)

    latitude_destino  = models.FloatField()
    longitude_destino = models.FloatField()
    endereco_destino  = models.CharField(max_length=255, blank=True)

    assentos_necessarios = models.PositiveIntegerField(default=1)
    status               = models.CharField(max_length=10, choices=STATUS_CHOICES, default="pending")

    criada_em = models.DateTimeField(auto_now_add=True)
    expiracao  = models.DateTimeField(default=default_expiracao)

    def __str__(self) -> str:
        return (
            f"Corrida de {self.passageiro.nome} → "
            f"{self.endereco_destino or 'Destino'} "
            f"({self.get_status_display()})"
        )
